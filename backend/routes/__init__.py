"""Blueprint registration."""

from flask import Flask

from backend.routes.flight_routes import flight_bp
from backend.routes.pirep_routes import pirep_bp


def register_routes(app: Flask) -> None:
    app.register_blueprint(flight_bp)
    app.register_blueprint(pirep_bp)
