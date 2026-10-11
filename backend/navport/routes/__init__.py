"""Blueprint registration.

Two blueprints serve the same handlers:

    v1      /api/v1/...   the API. Resource-oriented URLs, documented in the
                          OpenAPI description at /api/v1/openapi.json.
    legacy  /api/...      the original, unversioned URLs, kept as deprecated
                          aliases so clients written against them keep working
                          while they move over. See legacy_routes.py.

The version lives in the path because it is the most visible place for it:
a reader of a URL — or of an access log — can see which contract a client is
speaking without looking at its headers.
"""

from flask import Blueprint, Flask

api_v1 = Blueprint('v1', __name__, url_prefix='/api/v1')
legacy = Blueprint('legacy', __name__, url_prefix='/api')


def register_routes(app: Flask) -> None:
    # Importing these modules is what attaches their views to the blueprints,
    # so it has to happen before the blueprints are registered.
    from navport.routes import flight_routes, legacy_routes, meta, pirep_routes  # noqa: F401

    app.register_blueprint(api_v1)
    app.register_blueprint(legacy)

    # The bare root describes the API too, so opening the service's address in
    # a browser explains what it is instead of answering 404.
    app.add_url_rule('/', endpoint='root', view_func=meta.index)
