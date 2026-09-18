"""Risk scoring cases, including the one that reported a severe route as safe.

    python tests/test_risk.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.services.nlp_processor import SimpleNLPProcessor  # noqa: E402

nlp = SimpleNLPProcessor()


def route(severe: int = 0, significant: int = 0, clear: int = 0) -> list:
    return ([{'severity': 'Severe'}] * severe
            + [{'severity': 'Significant'}] * significant
            + [{'severity': 'Clear'}] * clear)


CASES = [
    # (name, timeline, expected level, expected percentage)
    ("clear end to end reads zero, not 20%",
     route(clear=11), "LOW RISK", 0.0),

    # This is the case the dashboard got wrong: the summary said
    # "OUTLOOK: Severe" and "WEATHER ALERT: 17 stations report severe weather"
    # while the risk panel said "31% - Low risk, conditions acceptable for
    # flight operations".
    ("one severe interval is never 'acceptable'",
     route(severe=1, significant=1, clear=9), "MODERATE RISK", 12.7),

    ("a quarter of the route severe is high",
     route(severe=3, clear=9), "HIGH RISK", 25.0),

    ("three severe intervals is high regardless of route length",
     route(severe=3, clear=40), "HIGH RISK", 7.0),

    ("two severe on a short route crosses the quarter mark",
     route(severe=2, clear=6), "HIGH RISK", 25.0),

    ("widespread significant weather is moderate without any severe",
     route(significant=6, clear=5), "MODERATE RISK", 21.8),

    ("a little significant weather stays low",
     route(significant=1, clear=10), "LOW RISK", 3.6),

    ("wall-to-wall severe pins the gauge",
     route(severe=8), "HIGH RISK", 100.0),

    ("an empty timeline does not divide by zero",
     [], "LOW RISK", 0.0),
]

failed = []
for name, timeline, want_level, want_pct in CASES:
    got = nlp.generate_risk_assessment(timeline)
    level, pct = got["risk_level"], got["risk_percentage"]
    ok = level == want_level and abs(pct - want_pct) < 0.05
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"          wanted {want_level} at {want_pct}%, got {level} at {pct}%")
        failed.append(name)

# The verdict must never contradict the worst interval on the route, which is
# what the dashboard shows beside it as OUTLOOK.
for severe in range(1, 12):
    result = nlp.generate_risk_assessment(route(severe=severe, clear=11 - severe))
    if result["risk_level"] == "LOW RISK":
        print(f"  FAIL  {severe} severe of 11 still reports LOW RISK")
        failed.append(f"{severe} severe of 11")

print(f"\n{len(CASES) + 11 - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
