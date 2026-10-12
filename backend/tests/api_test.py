"""End-to-end test of a running NavPort API.

Checks that every endpoint answers, that the API follows its own REST
conventions (versioned resource URLs, Problem Details errors, an index and an
OpenAPI description that agree with each other), that the old unversioned
addresses still work and announce their replacement, that malformed input is
rejected with 4xx rather than 500, that cross-origin access is granted to the
dashboard and to no one else, and that the security headers are present.
Exits non-zero if anything fails, so CI can gate on it.

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
V1 = "/api/v1"
PROBLEM_TYPE = "application/problem+json"

PASSED: list[str] = []
FAILED: list[str] = []


def open_url(req: urllib.request.Request, timeout: int):
    """urlopen, retrying a request that never reached the server.

    urllib raises URLError (and not its HTTPError subclass, which is a real
    answer) only when connecting, the TLS handshake or sending the request
    failed. A flaky Wi-Fi does that now and then, and it says nothing about
    the API. A timeout *waiting for the response* is not retried: that request
    did arrive, and a second copy would count against the rate limit.
    """
    for _ in range(2):
        try:
            return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as exc:
            print(f"  ..  network error before the request was sent ({exc.reason}), retrying")
            time.sleep(2)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310


def call(method: str, path: str, body=None, timeout: int = 90, headers=None):
    """Returns (status, headers, parsed_or_text). Never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    for name, value in (headers or {}).items():
        req.add_header(name, value)

    try:
        with open_url(req, timeout) as r:
            # The message object, not a dict of it: header names are
            # case-insensitive, and Azure's ingress lower-cases the ones it
            # doesn't recognise (deprecation:, sunset:).
            status, response_headers, raw = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, response_headers, raw = e.code, e.headers, e.read()

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


def is_problem(status: int, headers, payload) -> bool:
    """An RFC 9457 Problem Details response, consistent with its own status."""
    return (headers.get("Content-Type", "").startswith(PROBLEM_TYPE)
            and isinstance(payload, dict)
            and payload.get("status") == status
            and all(isinstance(payload.get(k), str) and payload.get(k) for k in ("type", "title", "detail")))


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
        status, _, payload = call("GET", f"{V1}/airports?codes=KJFK")
        if status != 429:
            return
        pause = 2
        if isinstance(payload, dict):
            pause = int(payload.get("retry_after_seconds") or 2) + 1
        print(f"  ..  rate limit still counting a previous run, waiting {pause}s")
        time.sleep(pause)


wait_out_rate_limit()
_, _, HEALTH = call("GET", f"{V1}/health")
IS_PRODUCTION = isinstance(HEALTH, dict) and HEALTH.get("environment") == "production"

# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------
section("Happy paths")

_, _, payload = expect_status(f"GET  {V1}/health", "GET", f"{V1}/health", 200)
check("  reports status ok", isinstance(payload, dict) and payload.get("status") == "ok",
      str(payload)[:120])

_, _, payload = expect_status(f"GET  {V1}/airports?codes=KJFK,EGLL", "GET",
                              f"{V1}/airports?codes=KJFK,EGLL", 200)
check("  resolves KJFK to an IATA code",
      isinstance(payload, dict) and payload.get("airports", {}).get("KJFK", {}).get("iata") == "JFK",
      str(payload)[:160])

_, _, payload = expect_status(f"GET  {V1}/airports/KJFK/alternates", "GET",
                              f"{V1}/airports/KJFK/alternates?radius=150&limit=3", 200)
check("  returns at least one alternate",
      isinstance(payload, dict) and len(payload.get("alternates", [])) > 0,
      str(payload)[:160])

_, _, payload = expect_status(f"GET  {V1}/airports/KJFK/pireps", "GET",
                              f"{V1}/airports/KJFK/pireps?distance=150&age=6", 200)
check("  returns a PIREP list", isinstance(payload, dict) and "pireps" in payload,
      str(payload)[:120])

_, _, payload = expect_status(f"POST {V1}/flight-plans/parse", "POST",
                              f"{V1}/flight-plans/parse", 200,
                              {"text": "fly from KJFK to KLAX via KORD at 450 knots"})
plan = payload.get("flight_plan", {}) if isinstance(payload, dict) else {}
check("  extracts departure and destination",
      plan.get("departure") == "KJFK" and plan.get("destination") == "KLAX",
      str(plan)[:160])

departure_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
_, _, payload = expect_status(f"POST {V1}/briefings", "POST", f"{V1}/briefings", 200,
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
    with open_url(req, 30) as r:
        return r.headers.get("Content-Encoding", "identity"), len(r.read())


batch = ",".join(["KJFK", "KLAX", "KORD", "KDEN", "KSEA", "KSFO", "KBOS", "KATL", "KMIA", "KDFW", "EGLL", "LFPG"])
encoding, size = encoding_of(f"{V1}/airports?codes={batch}")
check("  a large JSON response is gzipped", encoding == "gzip", f"{encoding}, {size / 1024:.1f} KB")

# --------------------------------------------------------------------------
# REST conventions
# --------------------------------------------------------------------------
section("REST design")

# The index is the one address a client needs to know; everything else is a
# link from it.
_, _, index = expect_status(f"GET  {V1}", "GET", V1, 200)
links = index.get("links", {}) if isinstance(index, dict) else {}
check("  links to itself and to every resource",
      links.get("self") == V1 and {"openapi", "health", "airport", "briefings"} <= set(links),
      str(links)[:160])

_, _, root = expect_status("GET  / (the service's bare address)", "GET", "/", 200)
check("  explains the API instead of a 404",
      isinstance(root, dict) and root.get("service") == "NavPort API", str(root)[:120])

# A single airport is a resource with its own URL, and links to the
# resources beneath it.
status, headers, airport = expect_status(f"GET  {V1}/airports/KJFK", "GET", f"{V1}/airports/KJFK", 200)
airport_links = airport.get("links", {}) if isinstance(airport, dict) else {}
check("  is the airport, with links to its alternates and PIREPs",
      isinstance(airport, dict) and airport.get("iata") == "JFK"
      and airport_links.get("self") == f"{V1}/airports/KJFK"
      and airport_links.get("alternates") == f"{V1}/airports/KJFK/alternates"
      and airport_links.get("pilot_reports") == f"{V1}/airports/KJFK/pireps",
      str(airport_links)[:160])
check("  is cacheable — an airport doesn't move",
      "public" in headers.get("Cache-Control", ""), headers.get("Cache-Control", ""))

# Errors: the status code says what kind, the Problem Details body says why.
status, headers, payload = expect_status(f"GET  {V1}/airports/ZZZZ (unknown)", "GET", f"{V1}/airports/ZZZZ", 404)
check("  is a Problem Details response (RFC 9457)", is_problem(status, headers, payload),
      f"{headers.get('Content-Type')}: {str(payload)[:120]}")
check("  says which resource", isinstance(payload, dict) and payload.get("instance") == f"{V1}/airports/ZZZZ",
      str(payload)[:120])

status, headers, payload = expect_status(f"GET  {V1}/no-such-thing", "GET", f"{V1}/no-such-thing", 404)
check("  is a Problem Details response too", is_problem(status, headers, payload), str(payload)[:120])

# RFC 9110: a 405 must say which methods the resource does support.
status, headers, payload = expect_status(f"DELETE {V1}/briefings", "DELETE", f"{V1}/briefings", 405)
check("  says what is allowed (Allow: POST)", "POST" in headers.get("Allow", ""),
      f"Allow: {headers.get('Allow')!r}")
check("  is a Problem Details response", is_problem(status, headers, payload), str(payload)[:120])

# The machine-readable contract, and that it describes what the index lists.
status, headers, spec = expect_status(f"GET  {V1}/openapi.json", "GET", f"{V1}/openapi.json", 200)
spec = spec if isinstance(spec, dict) else {}
check("  is OpenAPI 3.1", str(spec.get("openapi", "")).startswith("3.1."), str(spec.get("openapi")))
documented = set(spec.get("paths", {}))
undocumented = sorted({link.split("?")[0] for link in links.values()} - documented)
check("  documents every endpoint the index links to", not undocumented, f"missing {undocumented}")
legacy_paths = [p for p in documented if not p.startswith(V1)]
check("  marks the unversioned addresses deprecated",
      legacy_paths and all(op.get("deprecated") for p in legacy_paths for op in spec["paths"][p].values()),
      f"{len(legacy_paths)} unversioned paths")

# --------------------------------------------------------------------------
# The original addresses, before /api/v1
# --------------------------------------------------------------------------
section("Deprecated aliases")

# Each old address must still work — a client written against it can't be
# broken the day v1 ships — and must say, in standard headers, that it is
# retired (Deprecation, RFC 9745), when it may go (Sunset, RFC 8594), and
# exactly where its replacement is (Link rel="successor-version").
ALIASES = [
    ("GET",  "/api/health",                            None, 200, f"{V1}/health"),
    ("GET",  "/api/airports?codes=KJFK",               None, 200, f"{V1}/airports"),
    ("GET",  "/api/alternates/KJFK?radius=100&limit=2", None, 200, f"{V1}/airports/KJFK/alternates"),
    ("GET",  "/api/pirep-reports/KJFK?age=2",          None, 200, f"{V1}/airports/KJFK/pireps"),
    ("POST", "/api/process-natural-language", {"text": "KJFK to KLAX"}, 200, f"{V1}/flight-plans/parse"),
    ("POST", "/api/enhanced-flight-plan",     {"departure": "K"},       400, f"{V1}/briefings"),
]
for method, path, body, want, successor in ALIASES:
    status, headers, payload = expect_status(f"{method:4} {path.split('?')[0]}", method, path, want, body)
    link = headers.get("Link", "")
    check(f"  announces {successor} as its successor",
          bool(headers.get("Deprecation")) and bool(headers.get("Sunset"))
          and f"<{successor}>" in link and 'rel="successor-version"' in link,
          f"Deprecation={headers.get('Deprecation')!r} Sunset={headers.get('Sunset')!r} Link={link!r}")

check("  an old-style error keeps its 'error' member for old clients",
      isinstance(payload, dict) and payload.get("error") == payload.get("detail") and payload.get("error"),
      str(payload)[:160])

_, headers, _ = call("GET", f"{V1}/health")
check("  /api/v1 itself is not marked deprecated", "Deprecation" not in headers,
      f"Deprecation={headers.get('Deprecation')!r}")

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
_, headers, _ = call("GET", f"{V1}/health", headers={"Origin": ALLOWED_ORIGIN})
granted = headers.get("Access-Control-Allow-Origin", "")
check(f"allows the dashboard's origin ({ALLOWED_ORIGIN})", granted in (ALLOWED_ORIGIN, "*"),
      f"got {granted!r}")

# A briefing is a JSON POST, which the browser sends only after a preflight
# OPTIONS request has been approved.
status, headers, _ = call("OPTIONS", f"{V1}/briefings", headers={
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
    _, headers, _ = call("GET", f"{V1}/health", headers={"Origin": FOREIGN_ORIGIN})
    leaked = headers.get("Access-Control-Allow-Origin")
    check("refuses an origin it doesn't know", not leaked, f"got {leaked!r}")
else:
    print("  SKIP  refusal of unknown origins — development mode allows any origin by design")

# --------------------------------------------------------------------------
# Malformed input must be a 4xx, never a 500
# --------------------------------------------------------------------------
section("Input validation (bad input must not 500)")

BRIEFINGS = f"{V1}/briefings"
PARSE = f"{V1}/flight-plans/parse"
rejected = [
    expect_status("no codes",            "GET",  f"{V1}/airports", 400),
    expect_status("too many codes",      "GET",  f"{V1}/airports?codes=" + ",".join(["KJFK"] * 201), 400),
    expect_status("malformed airport",   "GET",  f"{V1}/airports/K!", 400),
    expect_status("empty POST body",     "POST", PARSE, 400),
    expect_status("empty text",          "POST", PARSE, 400, {"text": ""}),
    expect_status("oversized text",      "POST", PARSE, 400, {"text": "x" * 20_000}),
    expect_status("missing route",       "POST", BRIEFINGS, 400, {}),
    expect_status("null idents",         "POST", BRIEFINGS, 400, {"departure": None, "destination": None}),
    expect_status("non-numeric speed",   "POST", BRIEFINGS, 400,
                  {"departure": "KJFK", "destination": "KLAX", "cruise_speed": "fast"}),
    expect_status("malformed ICAO",      "POST", BRIEFINGS, 400, {"departure": "K", "destination": "!!!!"}),
    expect_status("waypoints not a list", "POST", BRIEFINGS, 400,
                  {"departure": "KJFK", "destination": "KLAX", "waypoints": "KORD"}),
    expect_status("too many waypoints",  "POST", BRIEFINGS, 400,
                  {"departure": "KJFK", "destination": "KLAX", "waypoints": ["KORD"] * 30}),
    # Werkzeug may collapse the traversal in routing before our validator sees
    # it; either a 400 from validation or a 404 from routing means it went
    # nowhere.
    expect_status("path traversal",      "GET",  f"{V1}/airports/..%2F..%2Fetc%2Fpasswd/alternates", (400, 404)),
    expect_status("param injection",     "GET",  f"{V1}/airports/KJFK%26id%3DKLAX/pireps", 400),
    expect_status("non-numeric radius",  "GET",  f"{V1}/airports/KJFK/alternates?radius=abc", 400),
    expect_status("wrong method",        "GET",  BRIEFINGS, 405),
]
not_problems = [f"{status}" for status, headers, payload in rejected if not is_problem(status, headers, payload)]
check("every rejection above is Problem Details", not not_problems, f"{len(not_problems)} were not")

# --------------------------------------------------------------------------
# Errors must not leak internals
# --------------------------------------------------------------------------
section("Error hygiene")

_, _, payload = call("POST", BRIEFINGS, {"departure": "ZZZZ", "destination": "ZZZY"})
message = json.dumps(payload)
for leak in ("Traceback", "File \"", "navport/", "navport\\\\", "backend/", "site-packages"):
    check(f"error body hides '{leak}'", leak not in message, message[:160])

# --------------------------------------------------------------------------
# Security headers
# --------------------------------------------------------------------------
section("Security headers")

_, headers, _ = call("GET", f"{V1}/health")
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
# Each worker process counts separately, so the real ceiling is the limit
# times the number of workers: 60 x 2 on Azure. A burst of only limit + 15
# passed in Docker, where one worker happened to take nearly every
# connection, and failed on Azure, whose ingress spreads them evenly.
limits = (HEALTH.get("limits", {}) or {}) if isinstance(HEALTH, dict) else {}
limit = limits.get("requests_per_window", 60)
workers = limits.get("worker_processes", 1)
ceiling = limit * workers

if ceiling > 500:
    print(f"  SKIP  limiter allows {ceiling}/window — too high to test cheaply")
else:
    burst = ceiling + 15
    responses = [call("GET", f"{V1}/airports?codes=KJFK") for _ in range(burst)]
    refused = [(status, headers, payload) for status, headers, payload in responses if status == 429]
    check(f"burst of {burst} requests (limit {limit} x {workers} worker processes) gets throttled",
          bool(refused),
          f"{len(refused)} refused" if refused else "no 429 at all — the limiter may be disabled")
    if refused:
        status, headers, payload = refused[0]
        check("  the 429 says when to retry (Retry-After)", headers.get("Retry-After", "").isdigit(),
              f"Retry-After: {headers.get('Retry-After')!r}")
        check("  and is Problem Details", is_problem(status, headers, payload), str(payload)[:120])

# --------------------------------------------------------------------------
section("Result")
print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("\n  Failures:")
    for name in FAILED:
        print(f"    - {name}")
sys.exit(1 if FAILED else 0)
