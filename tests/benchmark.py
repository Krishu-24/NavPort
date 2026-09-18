"""Measure what the efficiency work actually bought.

Reports transfer sizes with and without gzip, and briefing latency cold
(empty cache) versus warm. Run against a server started with a relaxed rate
limit, otherwise the limiter refuses the burst:

    NAVPORT_RATE_LIMIT=10000 NAVPORT_BRIEFING_RATE_LIMIT=10000 python run.py
    python tests/benchmark.py
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")


def get(path: str, gzip_on: bool):
    req = urllib.request.Request(BASE + path)
    if gzip_on:
        req.add_header("Accept-Encoding", "gzip")
    else:
        req.add_header("Accept-Encoding", "identity")

    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
        encoding = r.headers.get("Content-Encoding", "identity")
    return time.perf_counter() - start, len(raw), encoding


def briefing(destination: str = "KBOS"):
    body = json.dumps({
        "departure": "KJFK",
        "destination": destination,
        "waypoints": [],
        "cruise_speed": 450,
        "departure_time": (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
    }).encode()

    req = urllib.request.Request(BASE + "/api/enhanced-flight-plan", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept-Encoding", "gzip")

    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return time.perf_counter() - start, len(raw)


ASSETS = [
    ("index.html", "/"),
    ("css/tokens.css", "/css/tokens.css"),
    ("css/layout.css", "/css/layout.css"),
    ("css/components.css", "/css/components.css"),
    ("css/dashboard.css", "/css/dashboard.css"),
    ("js/main.js", "/js/main.js"),
    ("js/views/timeline.js", "/js/views/timeline.js"),
    ("js/views/charts.js", "/js/views/charts.js"),
]

print("Transfer size — the app shell every cold start downloads")
print("-" * 66)
print(f"  {'asset':24s} {'identity':>11s} {'gzip':>9s} {'saved':>8s}")

total_plain = total_gzip = 0
for label, path in ASSETS:
    _, plain, _ = get(path, False)
    _, compressed, encoding = get(path, True)
    total_plain += plain
    total_gzip += compressed
    saved = 100 - compressed * 100 / plain if plain else 0
    flag = "" if encoding == "gzip" else "  (not compressed)"
    print(f"  {label:24s} {plain / 1024:8.1f} KB {compressed / 1024:6.1f} KB {saved:6.0f}%{flag}")

print(f"  {'TOTAL':24s} {total_plain / 1024:8.1f} KB {total_gzip / 1024:6.1f} KB "
      f"{100 - total_gzip * 100 / total_plain:6.0f}%")

print()
print("Briefing latency — upstream cache cold vs warm")
print("-" * 66)

# A route nobody has asked for yet, so every upstream call is a real fetch.
cold_seconds, cold_size = briefing("KBOS")
print(f"  cold (first request for the route) {cold_seconds * 1000:8.0f} ms   {cold_size / 1024:6.1f} KB on the wire")

warm = [briefing("KBOS")[0] for _ in range(3)]
print(f"  warm (same route, cached upstream) {sum(warm) / len(warm) * 1000:8.0f} ms   "
      f"min {min(warm) * 1000:.0f} ms, max {max(warm) * 1000:.0f} ms")

if min(warm) > 0:
    print(f"  speedup {cold_seconds / (sum(warm) / len(warm)):.0f}x")
