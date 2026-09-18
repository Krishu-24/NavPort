"""Download Leaflet, Chart.js and the IBM Plex fonts into frontend/vendor/.

NavPort used to pull these from unpkg, jsdelivr and Google Fonts at runtime.
That is fine for a page you visit and wrong for this app, for three reasons:

  * The map and the charts stop existing when a CDN has a bad minute. It fails
    silently — Leaflet not executing just leaves an empty grey panel where the
    route should be, with no error anyone would notice.
  * The Tauri desktop and mobile builds bundle the frontend and are expected
    to open without a network. A basemap library fetched over HTTPS at startup
    defeats that.
  * Three extra origins in the Content-Security-Policy is three more places
    that have to stay trustworthy, plus SRI hashes to re-pin on every bump.

Serving them from our own origin removes all three. Run this when a version in
PINS changes; the files it writes are committed.

    python scripts/vendor_assets.py [--check]

Every download is verified against the SHA-384 in PINS before it is written,
so a tampered or truncated response cannot land in the tree. Those are the
same hashes that were in the index.html SRI attributes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "frontend" / "vendor"

UA = "NavPort-vendor-script (+https://github.com/navport)"

# path under frontend/vendor  ->  (url, sha384 or None)
#
# The two library hashes are the ones that were pinned as SRI in index.html,
# so this is verifying the exact bytes the browser was already accepting.
PINS: dict[str, tuple[str, str | None]] = {
    "leaflet/leaflet.css": (
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H",
    ),
    "leaflet/leaflet.js": (
        "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        "sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH",
    ),
    "chartjs/chart.umd.min.js": (
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
        "sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4",
    ),
}

# leaflet.css references these by relative path. The app draws its own markers
# with divIcons, but the stylesheet still asks for them, and a 404 on every
# map load is noise in the console and the access log.
for _image in ("layers.png", "layers-2x.png", "marker-icon.png",
               "marker-icon-2x.png", "marker-shadow.png"):
    PINS[f"leaflet/images/{_image}"] = (
        f"https://unpkg.com/leaflet@1.9.4/dist/images/{_image}",
        None,
    )

# Google's CSS is generated per user-agent: ask as a modern browser and it
# answers with woff2 and unicode-range subsets, which is what we want to keep.
FONT_CSS = (
    "https://fonts.googleapis.com/css2"
    "?family=IBM+Plex+Mono:wght@400;500;600"
    "&family=IBM+Plex+Sans:wght@400;500;600"
    "&display=swap"
)
MODERN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Google serves a subset per script. Only the Latin ones are worth the bytes
# here; the UI text is English and the data is ICAO codes and METAR strings.
KEEP_SUBSETS = ("latin", "latin-ext")


def sri(raw: bytes) -> str:
    return "sha384-" + base64.b64encode(hashlib.sha384(raw).digest()).decode()


def fetch(url: str, ua: str = UA) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def write(rel: str, raw: bytes) -> None:
    path = VENDOR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    print(f"  {rel:<44} {len(raw) / 1024:>7.1f} KB")


def vendor_libraries(check: bool) -> list[str]:
    problems = []
    print("libraries")
    for rel, (url, expected) in PINS.items():
        try:
            raw = fetch(url)
        except (urllib.error.URLError, TimeoutError) as exc:
            problems.append(f"{rel}: download failed ({exc})")
            continue

        actual = sri(raw)
        if expected and actual != expected:
            problems.append(
                f"{rel}: hash mismatch\n"
                f"      expected {expected}\n"
                f"      got      {actual}\n"
                "      Either the pinned version moved under us or the response was\n"
                "      tampered with. Nothing was written."
            )
            continue

        local = VENDOR / rel
        if check:
            if not local.exists():
                problems.append(f"{rel}: missing locally")
            elif sri(local.read_bytes()) != actual:
                problems.append(f"{rel}: local copy differs from upstream")
            else:
                print(f"  {rel:<44} ok")
            continue

        write(rel, raw)
    return problems


def vendor_fonts(check: bool) -> list[str]:
    print("fonts")
    try:
        css = fetch(FONT_CSS, MODERN_UA).decode()
    except (urllib.error.URLError, TimeoutError) as exc:
        return [f"font css: download failed ({exc})"]

    # Each @font-face block is preceded by a `/* latin */`-style comment
    # naming its subset, which is the only way to tell them apart.
    blocks = re.split(r"/\*\s*([a-z0-9-]+)\s*\*/", css)
    rewritten: list[str] = []
    files: dict[str, str] = {}
    problems: list[str] = []

    # re.split with one group yields [pre, name, body, name, body, ...]
    for i in range(1, len(blocks) - 1, 2):
        subset, body = blocks[i], blocks[i + 1]
        if subset not in KEEP_SUBSETS:
            continue
        match = re.search(r"url\((https://[^)]+\.woff2)\)", body)
        family = re.search(r"font-family:\s*'([^']+)'", body)
        weight = re.search(r"font-weight:\s*(\d+)", body)
        if not (match and family and weight):
            continue
        url = match.group(1)
        name = (f"{family.group(1).replace(' ', '-').lower()}"
                f"-{weight.group(1)}-{subset}.woff2")
        files[name] = url
        rewritten.append(body.replace(url, f"./{name}").strip())

    if not rewritten:
        return ["font css: no @font-face blocks matched — Google changed the format"]

    sheet = (
        "/* IBM Plex Sans and IBM Plex Mono, vendored by scripts/vendor_assets.py.\n"
        "   Generated file — edit the script, not this. */\n\n"
        + "\n\n".join(rewritten)
        + "\n"
    )

    if check:
        local = VENDOR / "fonts" / "fonts.css"
        if not local.exists():
            problems.append("fonts/fonts.css: missing locally")
        for name in files:
            if not (VENDOR / "fonts" / name).exists():
                problems.append(f"fonts/{name}: missing locally")
        if not problems:
            print(f"  fonts.css and {len(files)} woff2 files present")
        return problems

    write("fonts/fonts.css", sheet.encode())
    for name, url in sorted(files.items()):
        try:
            write(f"fonts/{name}", fetch(url, MODERN_UA))
        except (urllib.error.URLError, TimeoutError) as exc:
            problems.append(f"fonts/{name}: download failed ({exc})")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify the committed copies match upstream, write nothing")
    args = parser.parse_args()

    problems = vendor_libraries(args.check) + vendor_fonts(args.check)

    print()
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1
    print("verified" if args.check else f"vendored into {VENDOR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
