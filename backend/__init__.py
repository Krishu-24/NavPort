"""NavPort Flask application factory."""

import logging
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from backend.telemetry import install_telemetry

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )
    CORS(app)
    logging.basicConfig(level=logging.INFO)

    # Our own request line is richer than Werkzeug's, and two of them is noise.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    install_telemetry(app)

    from backend.routes import register_routes
    register_routes(app)

    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    return app
