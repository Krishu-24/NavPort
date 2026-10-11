"""The original, unversioned endpoints — kept as deprecated aliases.

Before /api/v1 existed, the API answered at addresses like
/api/enhanced-flight-plan and /api/pirep-reports/KJFK. Some of those names
describe actions rather than things, and none of them carried a version. The
v1 endpoints replace them; these aliases keep any client written against the
old addresses working while it moves over, instead of breaking it the moment
the new version ships.

Each alias runs exactly the same handler as its v1 successor, and says so in
its response with three standard headers:

    Deprecation: @1791763200                               RFC 9745 — retired since (a Unix time)
    Sunset: Tue, 12 Jan 2027 00:00:00 GMT                  RFC 8594 — may stop working after
    Link: </api/v1/briefings>; rel="successor-version"     RFC 5829 — use this instead

Errors from these aliases also keep the old `{"error": ...}` member alongside
the Problem Details fields (see problems.py), since that is what their clients
read.
"""

from datetime import datetime, timezone
from email.utils import format_datetime

from flask import request, url_for

from navport.routes import flight_routes, legacy, meta, pirep_routes

DEPRECATED_ON = datetime(2026, 10, 12, tzinfo=timezone.utc)
SUNSET_ON = datetime(2027, 1, 12, tzinfo=timezone.utc)

# (old rule under /api, v1 view, methods). The endpoint names match v1's, so
# rate limits and the successor link are worked out from the same name.
ALIASES = [
    ('',                              meta.index,                       ['GET']),
    ('/health',                       meta.health,                      ['GET']),
    ('/airports',                     flight_routes.list_airports,      ['GET']),
    ('/alternates/<icao>',            flight_routes.list_alternates,    ['GET']),
    ('/pirep-reports/<icao>',         pirep_routes.list_pireps,         ['GET']),
    ('/enhanced-flight-plan',         flight_routes.create_briefing,    ['POST']),
    ('/process-natural-language',     flight_routes.parse_flight_plan,  ['POST']),
]

for rule, view, methods in ALIASES:
    legacy.add_url_rule(rule, endpoint=view.__name__, view_func=view, methods=methods)


@legacy.after_request
def _announce_deprecation(response):
    """Tell the caller this address is retired, and exactly where to go."""
    name = (request.endpoint or '').rsplit('.', 1)[-1]
    if not name:
        return response

    successor = url_for(f'v1.{name}', **(request.view_args or {}))
    response.headers['Deprecation'] = f'@{int(DEPRECATED_ON.timestamp())}'
    response.headers['Sunset'] = format_datetime(SUNSET_ON, usegmt=True)
    response.headers.add('Link', f'<{successor}>; rel="successor-version"')
    return response
