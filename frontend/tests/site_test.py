"""End-to-end test of a served NavPort dashboard.

Runs against any address the dashboard is served from — the local dev server,
the nginx container, or the live Azure Static Web App — and checks what a
browser depends on: every file the app and its service worker need is there,
with the right type, compressed where it should be, and under a
Content-Security-Policy that admits exactly what the page uses, including the
API it calls. Exits non-zero if anything fails.

    python frontend/tests/site_test.py [base_url]

base_url defaults to http://127.0.0.1:8080. The API has its own test:
backend/tests/api_test.py.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080").rstrip("/")

PASSED: list[str] = []
FAILED: list[str] = []


def call(path: str, gzip: bool = False):
    """Returns (status, headers, body_text). Never raises on HTTP errors."""
    req = urllib.request.Request(BASE + path)
    if gzip:
        req.add_header("Accept-Encoding", "gzip")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, headers, raw = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        status, headers, raw = e.code, dict(e.headers), e.read()
    if headers.get("Content-Encoding") == "gzip":
        return status, headers, raw          # leave compressed bodies alone
    return status, headers, raw.decode("utf-8", "replace")


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSED if ok else FAILED).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{f'  — {detail}' if detail else ''}")
    return ok


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def header(headers: dict, name: str) -> str:
    """Case-insensitive lookup: proxies and CDNs don't all preserve case."""
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def csp_directive(csp: str, name: str) -> list[str]:
    for part in csp.split(";"):
        tokens = part.split()
        if tokens and tokens[0] == name:
            return tokens[1:]
    return []


# --------------------------------------------------------------------------
section("The page")

status, headers, index = call("/")
check("GET  / -> 200", status == 200, f"got {status}")
check("  is the dashboard", "<!DOCTYPE html>" in str(index)[:200] and "NavPort" in str(index))
check("  viewport allows drawing into the safe area", "viewport-fit=cover" in str(index))

# The API address must be set before config.js reads it, so api-config.js has
# to be a plain script in <head>, ahead of the deferred module scripts.
config_at = str(index).find("js/api-config.js")
main_at = str(index).find("js/main.js")
check("  loads api-config.js before main.js", 0 <= config_at < main_at,
      f"api-config at {config_at}, main at {main_at}")

# --------------------------------------------------------------------------
section("Installable-app plumbing")

for path in ["/manifest.webmanifest", "/sw.js", "/offline.html",
             "/css/platform.css", "/js/native.js", "/js/config.js", "/js/api-config.js",
             "/js/ui/offline.js", "/assets/icons/icon-192.png",
             "/assets/icons/icon-512.png", "/assets/icons/maskable-192.png",
             "/assets/icons/maskable-512.png", "/assets/icons/apple-touch-icon.png",
             "/assets/icons/favicon.ico"]:
    status, _, _ = call(path)
    check(f"{path} -> 200", status == 200, f"got {status}")

_, headers, manifest_text = call("/manifest.webmanifest")
content_type = header(headers, "Content-Type")
check("  manifest is served as application/manifest+json",
      "application/manifest+json" in content_type, content_type)
try:
    manifest = json.loads(manifest_text)
except (TypeError, json.JSONDecodeError):
    manifest = {}
check("  manifest declares a maskable icon",
      any("maskable" in i.get("purpose", "") for i in manifest.get("icons", [])))
check("  manifest display mode is standalone", manifest.get("display") == "standalone")

_, headers, sw_source = call("/sw.js")
cache_control = header(headers, "Cache-Control")
check("  service worker is not cached", "no-cache" in cache_control, cache_control)

# Every file the service worker precaches must exist, or install silently
# degrades and the app has no offline shell.
precached = re.findall(r"^\s*'(/[^']*)',", str(sw_source), re.MULTILINE)
missing = [p for p in precached if call(p)[0] != 200]
check(f"  all {len(precached)} precached shell assets exist", not missing, f"missing: {missing}")

# --------------------------------------------------------------------------
section("Compression")


def encoding_of(path: str) -> tuple:
    _, headers, body = call(path, gzip=True)
    return header(headers, "Content-Encoding") or "identity", len(body)


for asset in ("/", "/css/dashboard.css", "/js/main.js",
              "/vendor/leaflet/leaflet.js", "/vendor/chartjs/chart.umd.min.js"):
    encoding, size = encoding_of(asset)
    check(f"{asset} is gzipped", encoding == "gzip", f"{encoding}, {size / 1024:.1f} KB")

# woff2 is already compressed; gzipping it again only burns CPU.
encoding, size = encoding_of("/vendor/fonts/ibm-plex-sans-400-latin.woff2")
check("woff2 is not re-compressed", encoding == "identity", f"{encoding}, {size / 1024:.1f} KB")

# --------------------------------------------------------------------------
section("Security headers")

_, headers, _ = call("/")
for name, expected in [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
]:
    value = header(headers, name)
    check(name, value == expected, f"got {value!r}")

server = header(headers, "Server")
check("Server header carries no version number", not re.search(r"\d+\.\d+", server), server)

csp = header(headers, "Content-Security-Policy")
check("Content-Security-Policy is present", bool(csp))
check("  no unfilled placeholder in the policy", "__API_ORIGIN__" not in csp,
      "staticwebapp.config.json was deployed without running site.py configure")

# The page calls the API on another origin. If connect-src doesn't name it,
# the browser blocks every briefing — silently, as far as the user can tell.
_, _, api_config = call("/js/api-config.js")
literal = re.search(r"""NAVPORT_API_BASE\s*=\s*["'](https?://[^"']+)["']""", str(api_config))
if literal:
    parts = urlsplit(literal.group(1))
    api_origin = f"{parts.scheme}://{parts.netloc}"
else:
    # The committed local default: port 8000 on whatever host served the page.
    api_origin = f"http://{urlsplit(BASE).hostname}:8000"
check(f"  CSP lets the page call its API ({api_origin})",
      api_origin in csp_directive(csp, "connect-src"), f"connect-src: {csp_directive(csp, 'connect-src')}")

# A CSP that blocks the app's own assets is worse than no CSP, because it
# fails silently — the basemap just renders blank. Rather than hard-coding the
# tile host here, pull every third-party origin the frontend actually asks for
# out of the source and confirm the policy admits each one.
origins = set()
for source in ("js/views/map.js", "index.html", "js/core/api.js"):
    _, _, body = call("/" + source)
    for match in re.finditer(r"https://([A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(body)):
        host = match.group(1)
        if not host.endswith(("w3.org", "schema.org", "tauri.app")):
            origins.add(host)

for host in sorted(origins):
    parent = host.split(".", 1)[1] if "." in host else host
    allowed = host in csp or f"*.{parent}" in csp
    check(f"  CSP allows {host}", allowed, "" if allowed else "not in any directive")

# Leaflet, Chart.js and IBM Plex are vendored under /vendor/ so that a CDN
# outage cannot blank the map, and so the packaged apps open without a
# network. A reintroduced <script src="https://..."> would undo both quietly.
external = re.findall(r'(?:src|href)="(https?://[^"]+)"', str(index))
check("index.html loads no third-party scripts or styles", not external, f"found: {external[:3]}")
for directive in ("script-src", "font-src"):
    ok = csp_directive(csp, directive) == ["'self'"]
    check(f"CSP names no origin in {directive}", ok, " ".join(csp_directive(csp, directive)))

# --------------------------------------------------------------------------
section("Result")
print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("\n  Failures:")
    for name in FAILED:
        print(f"    - {name}")
sys.exit(1 if FAILED else 0)
