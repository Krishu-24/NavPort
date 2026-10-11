"""NavPort API — Flask application factory.

This service is the API and nothing else. The dashboard is a separate static
site (frontend/ in the repository, Azure Static Web Apps in production) that
calls this one over HTTPS. Keeping them apart is what lets each be hosted on
the service that suits it, scaled independently, and redeployed without
touching the other.
"""

import logging

from flask import Flask

from navport import config
from navport.security import install_security
from navport.telemetry import install_telemetry


def create_app() -> Flask:
    # No static folder: this process serves JSON only. Leaving Flask's default
    # in place would quietly answer /static/... requests from a directory that
    # does not exist, which is confusing at best.
    app = Flask(__name__, static_folder=None)

    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    # Errors are Problem Details JSON for every caller (see problems.py);
    # there is no HTML error page to fall back on.
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

    # Every endpoint — the API index, health, the OpenAPI description and the
    # resources themselves — lives in navport/routes/.
    from navport.routes import register_routes
    register_routes(app)

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
        # A cross-origin script can read only a handful of "simple" response
        # headers unless they are listed here. These are the ones the API uses
        # to say something: when to retry, which methods a resource supports,
        # and that an address is deprecated and where its replacement is. The
        # API reference page shows them on every "Try it out" response.
        expose_headers=['Retry-After', 'Allow', 'Deprecation', 'Sunset', 'Link'],
        max_age=3600,
    )
