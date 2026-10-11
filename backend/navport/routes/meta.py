"""Endpoints about the API itself: its index, its health, and its contract."""

import time
from urllib.parse import unquote

from flask import jsonify, url_for

from navport import config
from navport.openapi import build_spec
from navport.routes import api_v1

STARTED_AT = time.time()

API_VERSION = '2.0'


def _template(endpoint: str, **placeholders) -> str:
    """A link with {placeholders} left in it — an RFC 6570 URI template.

    url_for percent-encodes the braces, which would turn the template into a
    literal path no client could fill in.
    """
    return unquote(url_for(endpoint, **{name: '{' + name + '}' for name in placeholders}))


@api_v1.route('', methods=['GET'])
def index():
    """What this service is, and where everything is.

    A client can start here and follow links rather than hard-coding every
    path, which is the point of listing them — and a person who opens the API's
    address in a browser gets an explanation rather than a 404.
    """
    return jsonify({
        'service': 'NavPort API',
        'version': API_VERSION,
        'description': 'Aviation weather and route risk briefings, as JSON over HTTPS.',
        'links': {
            'self': url_for('v1.index'),
            'openapi': url_for('v1.openapi'),
            'health': url_for('v1.health'),
            'airports': url_for('v1.list_airports') + '?codes={codes}',
            'airport': _template('v1.get_airport', icao=True),
            'alternates': _template('v1.list_alternates', icao=True),
            'pilot_reports': _template('v1.list_pireps', icao=True),
            'briefings': url_for('v1.create_briefing'),
            'parse_flight_plan': url_for('v1.parse_flight_plan'),
        },
    })


@api_v1.route('/health', methods=['GET'])
def health():
    """Liveness/readiness probe.

    Deliberately does not touch aviationweather.gov: an upstream outage must
    not make Azure think the container is unhealthy and restart it in a loop.
    It reports whether the bundled airport database loaded, which is the one
    dependency a failed start would silently lose.
    """
    from navport.services import airports

    known = airports.count()
    return jsonify({
        'status': 'ok' if known else 'degraded',
        'version': API_VERSION,
        'environment': config.ENV,
        # Seconds since this process started. Also how a deploy can tell the
        # new revision is the one answering, rather than an old one still up.
        'uptime_seconds': round(time.time() - STARTED_AT, 1),
        'airports_loaded': known,
        # Published so a client can back off before being refused, and so the
        # API test can size its burst to whatever is configured.
        'limits': {
            'requests_per_window': config.RATE_LIMIT_REQUESTS,
            'briefings_per_window': config.BRIEFING_RATE_LIMIT,
            'window_seconds': config.RATE_LIMIT_WINDOW_SECONDS,
        },
    }), (200 if known else 503)


@api_v1.route('/openapi.json', methods=['GET'])
def openapi():
    """The machine-readable contract (OpenAPI 3.1) — what Swagger UI renders."""
    response = jsonify(build_spec(API_VERSION))
    # The contract only changes with a deploy, unlike the weather.
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response
