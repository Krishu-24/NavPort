"""End-to-end smoke test against a running NavPort server.

Checks that every endpoint answers, that malformed input is rejected with 4xx
rather than 500, and that the security headers are present. Exits non-zero on
the first failure so CI can gate on it.

    python tests/smoke_test.py [base_url]
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")

PASSED: list[str] = []
FAILED: list[str] = []


def call(method: str, path: str, body=None, timeout: int = 90):
    """Returns (status, headers, parsed_or_text). Never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, headers, raw = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        status, headers, raw = e.code, dict(e.headers), e.read()

    text = raw.decode("utf-8", "replace")
    try:
        return status, headers, json.loads(text)
    except json.JSONDecodeError:
        return status, headers, text


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSED if ok else FAILED).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{f'  — {detail}' if detail else ''}")
    return ok


def expect_status(name: str, method: str, path: str, want, body=None) -> tuple:
    """`want` is a status code or a tuple of acceptable codes."""
    wanted = want if isinstance(want, tuple) else (want,)
    status, headers, payload = call(method, path, body)
    check(f"{name} -> {'/'.join(map(str, wanted))}", status in wanted, f"got {status}")
    return status, headers, payload


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def wait_out_rate_limit() -> None:
    """Don't start until this client has a full rate-limit budget.

    The last thing this file does is deliberately exhaust the limiter to prove
    it works, so a second run inside the same window — a CI retry, or just
    running it twice — would otherwise open with a screen of 429s that look
    like real failures.
    """
    for _ in range(4):
        status, _, payload = call("GET", "/api/health")
        if status != 429:
            return
        pause = 2
        if isinstance(payload, dict):
            pause = int(payload.get("retry_after_seconds") or 2) + 1
        print(f"  ..  rate limit still counting a previous run, waiting {pause}s")
        time.sleep(pause)


wait_out_rate_limit()

# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------
section("Happy paths")

_, headers, payload = expect_status("GET  /", "GET", "/", 200)
check("  serves the dashboard HTML", "<!DOCTYPE html>" in str(payload)[:200])

_, _, payload = expect_status("GET  /api/health", "GET", "/api/health", 200)
check("  reports status ok", isinstance(payload, dict) and payload.get("status") == "ok",
      str(payload)[:120])

_, _, payload = expect_status("GET  /api/airports", "GET", "/api/airports?codes=KJFK,EGLL", 200)
check("  resolves KJFK to an IATA code",
      isinstance(payload, dict) and payload.get("airports", {}).get("KJFK", {}).get("iata") == "JFK",
      str(payload)[:160])

_, _, payload = expect_status("GET  /api/alternates/KJFK", "GET",
                              "/api/alternates/KJFK?radius=150&limit=3", 200)
check("  returns at least one alternate",
      isinstance(payload, dict) and len(payload.get("alternates", [])) > 0,
      str(payload)[:160])

_, _, payload = expect_status("GET  /api/pirep-reports/KJFK", "GET",
                              "/api/pirep-reports/KJFK?distance=150&age=6", 200)
check("  returns a PIREP list", isinstance(payload, dict) and "pireps" in payload,
      str(payload)[:120])

_, _, payload = expect_status("POST /api/process-natural-language", "POST",
                              "/api/process-natural-language", 200,
                              {"text": "fly from KJFK to KLAX via KORD at 450 knots"})
plan = payload.get("flight_plan", {}) if isinstance(payload, dict) else {}
check("  extracts departure and destination",
      plan.get("departure") == "KJFK" and plan.get("destination") == "KLAX",
      str(plan)[:160])

departure_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
_, _, payload = expect_status("POST /api/enhanced-flight-plan", "POST",
                              "/api/enhanced-flight-plan", 200,
                              {"departure": "KJFK", "destination": "KBOS",
                               "waypoints": [], "cruise_speed": 450,
                               "departure_time": departure_time})
if isinstance(payload, dict):
    check("  builds a non-empty timeline", len(payload.get("timeline", [])) > 0)
    check("  scores the route risk",
          payload.get("risk_assessment", {}).get("risk_level")
          in ("LOW RISK", "MODERATE RISK", "HIGH RISK"),
          str(payload.get("risk_assessment"))[:120])
    check("  writes a plain-English briefing", bool(payload.get("nlp_briefing_summary")))
    check("  labels every NOTAM as demo data",
          all("Demo" in n.get("source", "") for n in payload.get("notams", [])),
          "a NOTAM is missing its demo-data label")

    # The dashboard puts the worst conditions on the route (OUTLOOK) directly
    # beside the verdict, so the two must agree. They used to be able to
    # disagree: the verdict averaged severity across intervals, so a route
    # with embedded thunderstorms could read "Severe" outlook and "Low risk —
    # conditions acceptable for flight operations" in the same panel.
    # tests/test_risk.py covers the logic; this catches it on live weather.
    assessment = payload.get("risk_assessment", {})
    outlook = payload.get("route", {}).get("overall_severity")
    level = assessment.get("risk_level")
    consistent = not (outlook == "Severe" and level == "LOW RISK")
    check("  verdict does not contradict the route outlook", consistent,
          "" if consistent else f"outlook {outlook} but {level}")

    severe = assessment.get("severe_segments", 0)
    sane = not (severe and level == "LOW RISK")
    check("  a severe interval is never called acceptable", sane,
          "" if sane else f"{severe} severe interval(s) but {level}")

# --------------------------------------------------------------------------
# Installable-app plumbing
# --------------------------------------------------------------------------
section("PWA assets")

for path in ["/manifest.webmanifest", "/sw.js", "/offline.html",
             "/css/platform.css", "/js/native.js", "/js/config.js",
             "/js/ui/offline.js", "/assets/icons/icon-192.png",
             "/assets/icons/icon-512.png", "/assets/icons/maskable-192.png",
             "/assets/icons/maskable-512.png", "/assets/icons/apple-touch-icon.png",
             "/assets/icons/favicon.ico"]:
    expect_status(path, "GET", path, 200)

_, headers, manifest = call("GET", "/manifest.webmanifest")
check("  manifest is served as application/manifest+json",
      "application/manifest+json" in headers.get("Content-Type", ""),
      headers.get("Content-Type", ""))
check("  manifest declares a maskable icon",
      any("maskable" in i.get("purpose", "") for i in manifest.get("icons", []))
      if isinstance(manifest, dict) else False)
check("  manifest display mode is standalone",
      isinstance(manifest, dict) and manifest.get("display") == "standalone")

_, headers, _ = call("GET", "/sw.js")
check("  service worker is not cached",
      "no-cache" in headers.get("Cache-Control", ""), headers.get("Cache-Control", ""))

# Every file the service worker precaches must exist, or install silently
# degrades and the app has no offline shell.
_, _, sw_source = call("GET", "/sw.js")
precached = re.findall(r"^\s*'(/[^']*)',", str(sw_source), re.MULTILINE)
missing = [p for p in precached if call("GET", p)[0] != 200]
check(f"  all {len(precached)} precached shell assets exist",
      not missing, f"missing: {missing}")

# Compression is the difference between an 82 KB and a 21 KB cold start.
# urllib sends no Accept-Encoding of its own, so it has to be asked for here.
def encoding_of(path: str) -> tuple:
    req = urllib.request.Request(BASE + path)
    req.add_header("Accept-Encoding", "gzip")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Content-Encoding", "identity"), len(r.read())


for asset in ("/css/dashboard.css", "/js/main.js", "/"):
    encoding, size = encoding_of(asset)
    check(f"  {asset} is gzipped", encoding == "gzip", f"{encoding}, {size / 1024:.1f} KB")

# The vendored libraries have to be reachable, and gzip matters most here:
# Chart.js and Leaflet are the two largest files the app serves.
for asset in ("/vendor/leaflet/leaflet.js", "/vendor/chartjs/chart.umd.min.js"):
    encoding, size = encoding_of(asset)
    check(f"  {asset} is gzipped", encoding == "gzip", f"{encoding}, {size / 1024:.1f} KB")

# woff2 is already compressed; gzipping it again only burns CPU.
encoding, size = encoding_of("/vendor/fonts/ibm-plex-sans-400-latin.woff2")
check("  woff2 is not re-compressed", encoding == "identity", f"{encoding}, {size / 1024:.1f} KB")

_, _, index = call("GET", "/")
check("  viewport allows drawing into the safe area",
      "viewport-fit=cover" in str(index))

# --------------------------------------------------------------------------
# Malformed input must be a 4xx, never a 500
# --------------------------------------------------------------------------
section("Input validation (bad input must not 500)")

expect_status("no codes",            "GET",  "/api/airports", 400)
expect_status("too many codes",      "GET",  "/api/airports?codes=" + ",".join(["KJFK"] * 201), 400)
expect_status("empty POST body",     "POST", "/api/process-natural-language", 400)
expect_status("empty text",          "POST", "/api/process-natural-language", 400, {"text": ""})
expect_status("oversized text",      "POST", "/api/process-natural-language", 400, {"text": "x" * 20_000})
expect_status("missing route",       "POST", "/api/enhanced-flight-plan", 400, {})
expect_status("null idents",         "POST", "/api/enhanced-flight-plan", 400,
              {"departure": None, "destination": None})
expect_status("non-numeric speed",   "POST", "/api/enhanced-flight-plan", 400,
              {"departure": "KJFK", "destination": "KLAX", "cruise_speed": "fast"})
expect_status("malformed ICAO",      "POST", "/api/enhanced-flight-plan", 400,
              {"departure": "K", "destination": "!!!!"})
expect_status("waypoints not a list", "POST", "/api/enhanced-flight-plan", 400,
              {"departure": "KJFK", "destination": "KLAX", "waypoints": "KORD"})
expect_status("too many waypoints",  "POST", "/api/enhanced-flight-plan", 400,
              {"departure": "KJFK", "destination": "KLAX", "waypoints": ["KORD"] * 30})
# Werkzeug may collapse the traversal in routing before our validator sees it;
# either a 400 from validation or a 404 from routing means it went nowhere.
expect_status("path traversal",      "GET",  "/api/alternates/..%2F..%2Fetc%2Fpasswd", (400, 404))
expect_status("param injection",     "GET",  "/api/pirep-reports/KJFK%26id%3DKLAX", 400)
expect_status("non-numeric radius",  "GET",  "/api/alternates/KJFK?radius=abc", 400)

# --------------------------------------------------------------------------
# Errors must not leak internals
# --------------------------------------------------------------------------
section("Error hygiene")

_, _, payload = call("POST", "/api/enhanced-flight-plan", {"departure": "ZZZZ", "destination": "ZZZY"})
message = json.dumps(payload)
for leak in ("Traceback", "File \"", "backend/", "backend\\\\", "site-packages"):
    check(f"error body hides '{leak}'", leak not in message, message[:160])

# --------------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------------
section("Security headers")

_, headers, _ = call("GET", "/")
for header, expected in [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy", None),
]:
    value = headers.get(header)
    ok = bool(value) if expected is None else value == expected
    check(f"{header}", ok, f"got {value!r}")

check("Server header does not advertise Werkzeug",
      "erkzeug" not in headers.get("Server", ""), headers.get("Server", ""))

# A CSP that blocks the app's own assets is worse than no CSP, because it
# fails silently — the basemap just renders blank. Rather than hard-coding the
# tile host here, pull every third-party origin the frontend actually asks for
# out of the source and confirm the policy admits each one.
csp = headers.get("Content-Security-Policy", "")
origins = set()
for source in ("js/views/map.js", "index.html", "js/core/api.js"):
    _, _, body = call("GET", "/" + source)
    if isinstance(body, dict):
        continue
    for match in re.finditer(r"https://([A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(body)):
        host = match.group(1)
        if not host.endswith(("w3.org", "schema.org", "tauri.app")):
            origins.add(host)

for host in sorted(origins):
    # A directive may list the host outright or cover it with a wildcard.
    parent = host.split(".", 1)[1] if "." in host else host
    allowed = host in csp or f"*.{parent}" in csp
    check(f"  CSP allows {host}", allowed, "" if allowed else "not in any directive")

# Leaflet, Chart.js and IBM Plex are vendored under /vendor/ so that a CDN
# outage cannot blank the map, and so the packaged apps open without a
# network. A reintroduced <script src="https://..."> would undo both quietly.
_, _, index = call("GET", "/")
external = re.findall(r'(?:src|href)="(https?://[^"]+)"', str(index))
check("index.html loads no third-party scripts or styles",
      not external, f"found: {external[:3]}")
for directive in ("script-src 'self';", "font-src 'self';"):
    name = directive.split()[0]
    ok = directive in csp + ";"
    check(f"CSP names no origin in {name}", ok, "" if ok else csp)

# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
section("Rate limiting")

# Sized from whatever the server reports rather than assuming the defaults —
# otherwise this fails spuriously against a deployment that raised the limit.
_, _, health = call("GET", "/api/health")
limit = (health.get("limits", {}) or {}).get("requests_per_window", 60) if isinstance(health, dict) else 60

if limit > 500:
    print(f"  SKIP  limiter is configured at {limit}/window — too high to test cheaply")
else:
    burst = limit + 15
    codes = [call("GET", "/api/airports?codes=KJFK")[0] for _ in range(burst)]
    throttled = codes.count(429)
    check(f"burst of {burst} requests (limit {limit}) gets throttled", throttled > 0,
          f"{throttled} refused"
          if throttled else "no 429 at all — the limiter may be disabled")

# --------------------------------------------------------------------------
section("Result")
print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("\n  Failures:")
    for name in FAILED:
        print(f"    - {name}")
sys.exit(1 if FAILED else 0)
