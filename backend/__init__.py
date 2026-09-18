"""NavPort Flask application factory."""

import logging
import time
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from backend import config
from backend.security import install_security
from backend.telemetry import install_telemetry

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

STARTED_AT = time.time()

# The service worker must be served from the site root to be allowed to control
# it, and the manifest has its own media type. Everything else falls through to
# Flask's static handler.
ROOT_FILES = {
    'sw.js': 'application/javascript',
    'manifest.webmanifest': 'application/manifest+json',
    'offline.html': 'text/html',
}


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )

    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    # Errors are JSON for API callers, and the native shells have no HTML error
    # page to fall back on.
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

    from backend.routes import register_routes
    register_routes(app)

    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    @app.route('/test-ui')
    @app.route('/test-ui/')
    def test_ui():
        """Sandbox for UI experiments. Not the production dashboard."""
        return send_from_directory(FRONTEND_DIR / 'test-ui', 'index.html')

    @app.route('/api/health')
    def health():
        """Liveness/readiness probe.

        Deliberately does not touch aviationweather.gov: an upstream outage
        must not make Azure think the container is unhealthy and restart it in
        a loop. It reports whether the bundled airport database loaded, which
        is the one dependency a failed start would silently lose.
        """
        from backend.services import airports

        known = airports.count()
        return jsonify({
            'status': 'ok' if known else 'degraded',
            'version': '2.0',
            'environment': config.ENV,
            'uptime_seconds': round(time.time() - STARTED_AT, 1),
            'airports_loaded': known,
            # Published so a client can back off before being refused, and so
            # the smoke test can size its burst to whatever is configured
            # rather than assuming the defaults.
            'limits': {
                'requests_per_window': config.RATE_LIMIT_REQUESTS,
                'briefings_per_window': config.BRIEFING_RATE_LIMIT,
                'window_seconds': config.RATE_LIMIT_WINDOW_SECONDS,
            },
        }), (200 if known else 503)

    for filename, mimetype in ROOT_FILES.items():
        _register_root_file(app, filename, mimetype)

    return app


def _register_root_file(app: Flask, filename: str, mimetype: str) -> None:
    """Serve one file from the frontend directory at the site root."""

    def handler(_filename=filename, _mimetype=mimetype):
        response = send_from_directory(FRONTEND_DIR, _filename, mimetype=_mimetype)
        # A cached service worker is a stuck service worker: the browser would
        # keep running the old one and never pick up a deploy.
        if _filename == 'sw.js':
            response.headers['Cache-Control'] = 'no-cache'
        return response

    app.add_url_rule(f'/{filename}', endpoint=f'root_{filename.replace(".", "_")}', view_func=handler)


def _install_cors(app: Flask) -> None:
    """Cross-origin access for the native shells, scoped to the API.

    flask-cors is given an explicit origin list in production (see
    `config.CORS_ORIGINS`) rather than the default wildcard, and is confined to
    `/api/*` so the static dashboard is never cross-origin readable.
    """
    from flask_cors import CORS

    CORS(
        app,
        resources={r"/api/*": {"origins": config.CORS_ORIGINS}},
        methods=['GET', 'POST', 'OPTIONS'],
        allow_headers=['Content-Type'],
        max_age=3600,
    )
