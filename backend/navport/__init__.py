"""NavPort API — Flask application factory.

This service is the API and nothing else. The dashboard is a separate static
site (frontend/ in the repository, Azure Static Web Apps in production) that
calls this one over HTTPS. Keeping them apart is what lets each be hosted on
the service that suits it, scaled independently, and redeployed without
touching the other.
"""

import logging
import time

from flask import Flask, jsonify

from navport import config
from navport.security import install_security
from navport.telemetry import install_telemetry

STARTED_AT = time.time()

API_VERSION = '2.0'


def create_app() -> Flask:
    # No static folder: this process serves JSON only. Leaving Flask's default
    # in place would quietly answer /static/... requests from a directory that
    # does not exist, which is confusing at best.
    app = Flask(__name__, static_folder=None)

    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    # Errors are JSON for every caller; there is no HTML error page to fall
    # back on.
    app.config['TRAP_HTTP_EXCEPTIONS'] = False
    # Keep the insertion order of response bodies, so a briefing reads in the
    # order it was built. Flask 2.3 moved this off app.config, where setting it
    # is silently ignored.
    app.json.sort_keys = False

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )
    # Our own request line is richer than Werkzeug's, and two of them is noise.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    _install_cors(app)
    install_security(app)

    if config.TELEMETRY_ENABLED:
        install_telemetry(app)

    from navport.routes import register_routes
    register_routes(app)

    @app.route('/')
    @app.route('/api')
    def index():
        """What this service is and where its endpoints are.

        Someone opening the API's address in a browser gets an explanation
        rather than a bare 404, and a client can discover the endpoints from
        one known URL instead of hard-coding every path.
        """
        return jsonify({
            'service': 'NavPort API',
            'version': API_VERSION,
            'description': 'Aviation weather and route risk briefings, as JSON over HTTPS.',
            'endpoints': {
                'health': {'method': 'GET', 'path': '/api/health'},
                'airports': {'method': 'GET', 'path': '/api/airports?codes={ICAO,...}'},
                'alternates': {'method': 'GET', 'path': '/api/alternates/{icao}'},
                'pilot_reports': {'method': 'GET', 'path': '/api/pirep-reports/{station}'},
                'briefing': {'method': 'POST', 'path': '/api/enhanced-flight-plan'},
                'parse_plan': {'method': 'POST', 'path': '/api/process-natural-language'},
            },
        })

    @app.route('/api/health')
    def health():
        """Liveness/readiness probe.

        Deliberately does not touch aviationweather.gov: an upstream outage
        must not make Azure think the container is unhealthy and restart it in
        a loop. It reports whether the bundled airport database loaded, which
        is the one dependency a failed start would silently lose.
        """
        from navport.services import airports

        known = airports.count()
        return jsonify({
            'status': 'ok' if known else 'degraded',
            'version': API_VERSION,
            'environment': config.ENV,
            'uptime_seconds': round(time.time() - STARTED_AT, 1),
            'airports_loaded': known,
            # Published so a client can back off before being refused, and so
            # the API test can size its burst to whatever is configured rather
            # than assuming the defaults.
            'limits': {
                'requests_per_window': config.RATE_LIMIT_REQUESTS,
                'briefings_per_window': config.BRIEFING_RATE_LIMIT,
                'window_seconds': config.RATE_LIMIT_WINDOW_SECONDS,
            },
        }), (200 if known else 503)

    return app


def _install_cors(app: Flask) -> None:
    """Cross-origin access to the API.

    The dashboard is served from a different origin than this API — a separate
    Static Web App in production, a separate local server in development — so
    every call it makes is cross-origin and the browser will only hand the
    response to the page if this service names that origin. The native shells
    have their own schemes (tauri://, capacitor://) and need the same.

    In production the allowlist is explicit (see `config.CORS_ORIGINS`), never
    the wildcard, which would let any website on the internet drive this API
    with a visitor's IP and burn the shared upstream quota.
    """
    from flask_cors import CORS

    CORS(
        app,
        resources={r"/api/*": {"origins": config.CORS_ORIGINS}},
        methods=['GET', 'POST', 'OPTIONS'],
        allow_headers=['Content-Type'],
        max_age=3600,
    )
