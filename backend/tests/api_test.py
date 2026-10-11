"""End-to-end test of a running NavPort API.

Checks that every endpoint answers, that malformed input is rejected with 4xx
rather than 500, that cross-origin access is granted to the dashboard and to
no one else, and that the security headers are present. Exits non-zero if
anything fails, so CI can gate on it.

    python backend/tests/api_test.py [base_url]

base_url defaults to http://127.0.0.1:8000. The CORS checks use an origin the
server is expected to allow — NAVPORT_TEST_ORIGIN, default
http://localhost:8080, which is what docker-compose.yml and CI configure.

The dashboard has its own test: frontend/tests/site_test.py.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
ALLOWED_ORIGIN = os.environ.get("NAVPORT_TEST_ORIGIN", "http://localhost:8080")
FOREIGN_ORIGIN = "https://not-navport.example"

PASSED: list[str] = []
FAILED: list[str] = []


def call(method: str, path: str, body=None, timeout: int = 90, headers=None):
    """Returns (status, headers, parsed_or_text). Never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        req.add_header(name, value)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, response_headers, raw = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        status, response_headers, raw = e.code, dict(e.headers), e.read()

    text = raw.decode("utf-8", "replace")
    try:
        return status, response_headers, json.loads(text)
    except json.JSONDecodeError:
        return status, response_headers, text


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
        status, _, payload = call("GET", "/api/airports?codes=KJFK")
        if status != 429:
            return
        pause = 2
        if isinstance(payload, dict):
            pause = int(payload.get("retry_after_seconds") or 2) + 1
        print(f"  ..  rate limit still counting a previous run, waiting {pause}s")
        time.sleep(pause)


wait_out_rate_limit()
_, _, HEALTH = call("GET", "/api/health")
IS_PRODUCTION = isinstance(HEALTH, dict) and HEALTH.get("environment") == "production"

# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------
section("Happy paths")

_, _, payload = expect_status("GET  /", "GET", "/", 200)
check("  describes the API and lists its endpoints",
      isinstance(payload, dict) and payload.get("service") == "NavPort API"
      and "briefing" in payload.get("endpoints", {}),
      str(payload)[:160])

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


# Compression: a briefing or a batch airport lookup is tens of kilobytes of
# JSON, and compresses several-fold. urllib sends no Accept-Encoding of its
# own, so it has to be asked for here.
def encoding_of(path: str) -> tuple:
    req = urllib.request.Request(BASE + path)
    req.add_header("Accept-Encoding", "gzip")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.headers.get("Content-Encoding", "identity"), len(r.read())


batch = ",".join(["KJFK", "KLAX", "KORD", "KDEN", "KSEA", "KSFO", "KBOS", "KATL", "KMIA", "KDFW", "EGLL", "LFPG"])
encoding, size = encoding_of(f"/api/airports?codes={batch}")
check("  a large JSON response is gzipped", encoding == "gzip", f"{encoding}, {size / 1024:.1f} KB")

# --------------------------------------------------------------------------
# The API is only the API
# --------------------------------------------------------------------------
section("Separation from the dashboard")

# The dashboard is a separate static site. If the API ever starts answering
# for its files again, the two have been re-coupled.
for path in ("/index.html", "/sw.js", "/css/dashboard.css", "/manifest.webmanifest"):
    expect_status(f"GET  {path}", "GET", path, 404)

# --------------------------------------------------------------------------
# Cross-origin access
# --------------------------------------------------------------------------
section("CORS")

# The dashboard calls this API from another origin, so the browser only hands
# it a response if the API names that origin. This is the setting that has to
# match the dashboard's real address in every deployment.
_, headers, _ = call("GET", "/api/health", headers={"Origin": ALLOWED_ORIGIN})
granted = headers.get("Access-Control-Allow-Origin", "")
check(f"allows the dashboard's origin ({ALLOWED_ORIGIN})", granted in (ALLOWED_ORIGIN, "*"),
      f"got {granted!r}")

# A briefing is a JSON POST, which the browser sends only after a preflight
# OPTIONS request has been approved.
status, headers, _ = call("OPTIONS", "/api/enhanced-flight-plan", headers={
    "Origin": ALLOWED_ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
})
check("preflight for a JSON POST is approved",
      status in (200, 204) and headers.get("Access-Control-Allow-Origin") in (ALLOWED_ORIGIN, "*")
      and "POST" in headers.get("Access-Control-Allow-Methods", ""),
      f"status {status}, allow-origin {headers.get('Access-Control-Allow-Origin')!r}, "
      f"allow-methods {headers.get('Access-Control-Allow-Methods')!r}")

if IS_PRODUCTION:
    _, headers, _ = call("GET", "/api/health", headers={"Origin": FOREIGN_ORIGIN})
    leaked = headers.get("Access-Control-Allow-Origin")
    check("refuses an origin it doesn't know", not leaked, f"got {leaked!r}")
else:
    print("  SKIP  refusal of unknown origins — development mode allows any origin by design")

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
expect_status("wrong method",        "GET",  "/api/enhanced-flight-plan", 405)

# --------------------------------------------------------------------------
# Errors must not leak internals
# --------------------------------------------------------------------------
section("Error hygiene")

_, _, payload = call("POST", "/api/enhanced-flight-plan", {"departure": "ZZZZ", "destination": "ZZZY"})
message = json.dumps(payload)
for leak in ("Traceback", "File \"", "navport/", "navport\\\\", "backend/", "site-packages"):
    check(f"error body hides '{leak}'", leak not in message, message[:160])

# --------------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------------
section("Security headers")

_, headers, _ = call("GET", "/api/health")
for header, expected in [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    # An API returns data, never a page, so its policy permits nothing.
    ("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"),
    # Weather goes stale in minutes; nothing between here and the browser may
    # keep a copy.
    ("Cache-Control", "no-store"),
]:
    value = headers.get(header)
    check(f"{header}", value == expected, f"got {value!r}")

# Naming the server software, and worse its version, tells a scanner which
# list of known vulnerabilities to try. Werkzeug includes its version; gunicorn
# ignores the app's Server header and writes its own unless told otherwise
# (see gunicorn.conf.py), so this checks what actually goes out on the wire.
server = headers.get("Server", "")
check("Server header names no server software",
      not any(name in server.lower() for name in ("werkzeug", "gunicorn", "python")), server)
check("Server header carries no version number", not re.search(r"\d+\.\d+", server), server)

# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
section("Rate limiting")

# Sized from whatever the server reports rather than assuming the defaults —
# otherwise this fails spuriously against a deployment that raised the limit.
limit = (HEALTH.get("limits", {}) or {}).get("requests_per_window", 60) if isinstance(HEALTH, dict) else 60

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
