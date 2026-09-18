"""Validate desktop/src-tauri/tauri.conf.json against the official Tauri v2 schema.

    python scripts/check_tauri_config.py

Worth having because a typo in this file doesn't fail until you have already
installed Rust, the Android SDK and the NDK and waited through a Cargo build.
Checking the shape up front costs a second instead.
"""

import json
import sys
import urllib.request
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "desktop" / "src-tauri" / "tauri.conf.json"
SCHEMA_URL = "https://schema.tauri.app/config/2"

REQUIRED_TOP_LEVEL = ["identifier"]


def resolve(schema: dict, node: dict) -> dict:
    """Follow a $ref (or the first branch of an allOf) to its definition."""
    definitions = schema.get("definitions") or schema.get("$defs") or {}

    ref = node.get("$ref")
    if not ref and "allOf" in node and node["allOf"]:
        ref = node["allOf"][0].get("$ref")
    if not ref and "anyOf" in node:
        for branch in node["anyOf"]:
            if branch.get("$ref"):
                ref = branch["$ref"]
                break

    if not ref:
        return node

    return definitions.get(ref.split("/")[-1], {})


def walk(schema: dict, node: dict, value, path: str, problems: list) -> None:
    """Report keys the schema doesn't define, recursing into nested objects."""
    node = resolve(schema, node)
    properties = node.get("properties")
    if not properties or not isinstance(value, dict):
        return

    for key, child in value.items():
        if key.startswith(("$", "//")):
            continue
        if key not in properties:
            problems.append(f"{path}.{key}" if path else key)
            continue
        walk(schema, properties[key], child, f"{path}.{key}" if path else key, problems)


def main() -> int:
    if not CONFIG.exists():
        print(f"Not found: {CONFIG}", file=sys.stderr)
        return 1

    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {CONFIG.name}: {exc}", file=sys.stderr)
        return 1

    print(f"{CONFIG.name} is valid JSON")

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in config]
    if missing:
        print(f"  MISSING required key(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"  required keys present: {', '.join(REQUIRED_TOP_LEVEL)}")

    try:
        request = urllib.request.Request(SCHEMA_URL, headers={"User-Agent": "NavPort-Config-Check/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            schema = json.load(response)
    except Exception as exc:
        print(f"  could not fetch the schema ({exc}) — skipping key validation")
        return 0

    problems: list = []
    walk(schema, schema, config, "", problems)

    if problems:
        print("\n  Keys the Tauri v2 schema does not define:", file=sys.stderr)
        for key in problems:
            print(f"    {key}", file=sys.stderr)
        print("\n  Tauri rejects unknown keys, so these would fail the build.", file=sys.stderr)
        return 1

    print("  every key matches the Tauri v2 schema")

    identifier = config.get("identifier", "")
    if identifier.endswith(".app") and identifier.count(".") < 2:
        print(f"  note: identifier {identifier!r} looks unusual; the convention is reverse-DNS")

    print(f"\nConfig OK — productName={config.get('productName')!r} "
          f"version={config.get('version')!r} identifier={identifier!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
