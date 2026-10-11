"""The API's contract, as an OpenAPI 3.1 document.

Served at GET /api/v1/openapi.json and rendered by the dashboard's API
reference page (frontend/public/docs/), where every endpoint can be tried
live. Built in Python rather than hand-written JSON so that the limits it
documents — waypoints per route, codes per lookup, text length — are read from
the same config values the validators enforce, and can't drift from them.

backend/tests/api_test.py checks this document against the running API: every
endpoint the index lists must be described here.
"""

from navport import config

ICAO_PATTERN = '^[A-Za-z0-9]{4}$'


def _ref(name: str) -> dict:
    return {'$ref': f'#/components/schemas/{name}'}


def _response(name: str) -> dict:
    return {'$ref': f'#/components/responses/{name}'}


def _json(schema: dict, description: str, example=None) -> dict:
    content = {'schema': schema}
    if example is not None:
        content['example'] = example
    return {'description': description, 'content': {'application/json': content}}


ICAO_PATH_PARAM = {
    'name': 'icao',
    'in': 'path',
    'required': True,
    'description': 'Four-character ICAO airport identifier. Case-insensitive.',
    'schema': {'type': 'string', 'pattern': ICAO_PATTERN, 'example': 'KJFK'},
}


def _schemas() -> dict:
    nullable_string = {'type': ['string', 'null']}
    return {
        'Problem': {
            'type': 'object',
            'description': 'RFC 9457 Problem Details. Every error response has this shape and the '
                           'media type application/problem+json.',
            'required': ['type', 'title', 'status', 'detail'],
            'properties': {
                'type': {'type': 'string', 'example': 'about:blank'},
                'title': {'type': 'string', 'description': 'Standard phrase for the status code.',
                          'example': 'Bad Request'},
                'status': {'type': 'integer', 'example': 400},
                'detail': {'type': 'string', 'description': 'What went wrong with this request.',
                           'example': "departure must be a 4-character ICAO code, e.g. KJFK — got 'K'"},
                'instance': {'type': 'string', 'description': 'The path that produced the error.',
                             'example': '/api/v1/briefings'},
                'retry_after_seconds': {'type': 'integer',
                                        'description': 'On 429 only: seconds until the budget refills.'},
            },
        },
        'ApiIndex': {
            'type': 'object',
            'properties': {
                'service': {'type': 'string'},
                'version': {'type': 'string'},
                'description': {'type': 'string'},
                'links': {'type': 'object', 'additionalProperties': {'type': 'string'},
                          'description': 'Where each resource lives. {placeholders} are URI templates.'},
            },
        },
        'Health': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'enum': ['ok', 'degraded']},
                'version': {'type': 'string'},
                'environment': {'type': 'string', 'example': 'production'},
                'uptime_seconds': {'type': 'number',
                                   'description': 'Seconds since this process started. A fresh deploy reads low.'},
                'airports_loaded': {'type': 'integer', 'example': 34225},
                'limits': {
                    'type': 'object',
                    'properties': {
                        'requests_per_window': {'type': 'integer'},
                        'briefings_per_window': {'type': 'integer'},
                        'window_seconds': {'type': 'integer'},
                    },
                },
            },
        },
        'Airport': {
            'type': 'object',
            'description': 'Identity of an airport. For an identifier the database does not know, '
                           'every field except icao is null.',
            'properties': {
                'icao': {'type': 'string', 'example': 'KJFK'},
                'iata': {**nullable_string, 'example': 'JFK'},
                'name': {**nullable_string, 'example': 'John F Kennedy International Airport'},
                'city': {**nullable_string, 'example': 'New York'},
                'country': {**nullable_string, 'example': 'US'},
                'kind': {**nullable_string, 'example': 'Large airport'},
                'elevation_ft': {'type': ['integer', 'null'], 'example': 13},
            },
        },
        'AirportResource': {
            'allOf': [
                _ref('Airport'),
                {
                    'type': 'object',
                    'properties': {
                        'lat': {'type': ['number', 'null'], 'example': 40.6399},
                        'lon': {'type': ['number', 'null'], 'example': -73.7787},
                        'links': {
                            'type': 'object',
                            'description': 'Related resources (hypermedia).',
                            'properties': {
                                'self': {'type': 'string', 'example': '/api/v1/airports/KJFK'},
                                'alternates': {'type': 'string', 'example': '/api/v1/airports/KJFK/alternates'},
                                'pilot_reports': {'type': 'string', 'example': '/api/v1/airports/KJFK/pireps'},
                            },
                        },
                    },
                },
            ],
        },
        'AirportBatch': {
            'type': 'object',
            'properties': {
                'airports': {'type': 'object', 'additionalProperties': _ref('Airport'),
                             'description': 'Keyed by identifier, upper-cased.'},
                'known': {'type': 'integer', 'description': 'Airports in the bundled database.'},
            },
        },
        'Alternate': {
            'type': 'object',
            'properties': {
                'station': {'type': 'string'},
                'name': {'type': 'string'},
                'identity': _ref('Airport'),
                'distance_nm': {'type': 'integer'},
                'bearing': {'type': 'number'},
                'compass': {'type': 'string', 'example': 'NE'},
                'flight_category': {'type': 'string', 'enum': ['VFR', 'MVFR', 'IFR', 'LIFR']},
                'improvement': {'type': 'boolean',
                                'description': 'Better conditions than the airport it is an alternate for.'},
                'ceiling_ft': {'type': ['integer', 'null']},
                'visibility_sm': {'type': ['number', 'null']},
                'wind_dir': {'type': ['number', 'null']},
                'wind_speed': {'type': 'number'},
                'wind_gust': {'type': ['number', 'null']},
                'raw': {'type': 'string', 'description': 'The METAR as reported.'},
            },
        },
        'Alternates': {
            'type': 'object',
            'properties': {
                'station': {'type': 'string'},
                'name': {'type': 'string'},
                'observed': {'type': 'boolean', 'description': 'Whether the airport itself has a current report.'},
                'flight_category': {'type': ['string', 'null']},
                'ceiling_ft': {'type': ['integer', 'null']},
                'visibility_sm': {'type': ['number', 'null']},
                'raw': {'type': 'string'},
                'searched_nm': {'type': 'integer'},
                'alternates': {'type': 'array', 'items': _ref('Alternate')},
                'total_found': {'type': 'integer'},
            },
        },
        'PilotReport': {
            'type': 'object',
            'properties': {
                'raw': {'type': 'string'},
                'type': {'type': 'string', 'description': 'PIREP (routine) or AIREP / urgent.'},
                'obs_time': {},
                'receipt_time': {},
                'lat': {'type': ['number', 'null']},
                'lon': {'type': ['number', 'null']},
                'altitude_ft_msl': {'type': ['number', 'null']},
                'station': {'type': ['string', 'null']},
                'turbulence': {},
                'icing': {},
                'sky': {},
                'temp_c': {'type': ['number', 'null']},
                'aircraft': {'type': ['string', 'null']},
                'remarks': {'type': ['string', 'null']},
                'summary': {'type': 'string', 'description': 'Plain-English version. Omitted when raw=true.'},
            },
        },
        'PilotReports': {
            'type': 'object',
            'properties': {
                'station_id': {'type': 'string'},
                'pireps': {'type': 'array', 'items': _ref('PilotReport')},
                'count': {'type': 'integer'},
                'show_raw': {'type': 'boolean'},
            },
        },
        'FlightPlan': {
            'type': 'object',
            'required': ['departure', 'destination'],
            'properties': {
                'departure': {'type': 'string', 'pattern': ICAO_PATTERN, 'example': 'KJFK'},
                'destination': {'type': 'string', 'pattern': ICAO_PATTERN, 'example': 'KLAX'},
                'waypoints': {
                    'type': 'array',
                    'items': {'type': 'string', 'pattern': ICAO_PATTERN},
                    'maxItems': config.MAX_WAYPOINTS,
                    'default': [],
                    'example': ['KORD'],
                },
                'cruise_speed': {'type': 'integer', 'minimum': 40, 'maximum': 900, 'default': 450,
                                 'description': 'Knots. Out-of-range values are clamped.'},
                'departure_time': {
                    'type': 'string',
                    'description': f'UTC, ISO-8601 (e.g. 2026-10-12T14:30). Defaults to now. Must be within '
                                   f'{config.MAX_PAST_DEPARTURE_DAYS} days in the past and '
                                   f'{config.MAX_FUTURE_DEPARTURE_HOURS} hours in the future — '
                                   f'the window the upstream weather service can answer for.',
                },
            },
        },
        'Briefing': {
            'type': 'object',
            'description': 'A full route briefing. Large: tens of kilobytes for a typical route.',
            'properties': {
                'route': {'type': 'object', 'description': 'Distance, time, worst category, overall severity.'},
                'flight_segments': {'type': 'array', 'items': {'type': 'object'}},
                'timeline': {'type': 'array', 'items': {'type': 'object'},
                             'description': '15-minute intervals with conditions and severity.'},
                'weather_summary': {'type': 'object', 'description': 'Counts of each upstream product used.'},
                'notams': {'type': 'array', 'items': {'type': 'object'},
                           'description': 'Simulated — each is labelled "Demo Data (Time-Based)".'},
                'airports': {'type': 'object', 'additionalProperties': _ref('Airport')},
                'airfields': {'type': 'object', 'description': 'Departure and destination field conditions.'},
                'nlp_briefing_summary': {'type': 'string'},
                'risk_assessment': {
                    'type': 'object',
                    'properties': {
                        'risk_level': {'type': 'string', 'enum': ['LOW RISK', 'MODERATE RISK', 'HIGH RISK']},
                        'risk_percentage': {'type': 'number'},
                        'recommendation': {'type': 'string'},
                    },
                },
            },
        },
        'ParseRequest': {
            'type': 'object',
            'required': ['text'],
            'properties': {
                'text': {'type': 'string', 'maxLength': config.MAX_TEXT_LENGTH,
                         'example': 'fly from KJFK to KLAX via KORD at 450 knots'},
            },
        },
        'ParseResult': {
            'type': 'object',
            'properties': {
                'flight_plan': _ref('FlightPlan'),
                'original_text': {'type': 'string'},
                'success': {'type': 'boolean'},
            },
        },
    }


def _responses() -> dict:
    def problem(description: str, **extra) -> dict:
        response = {
            'description': description,
            'content': {'application/problem+json': {'schema': _ref('Problem')}},
        }
        response.update(extra)
        return response

    return {
        'BadRequest': problem('The request was invalid. `detail` says which field and why.'),
        'NotFound': problem('No such resource.'),
        'PayloadTooLarge': problem(f'Request body over {config.MAX_CONTENT_LENGTH // 1024} KB.'),
        'TooManyRequests': problem(
            'Rate limit reached for this client.',
            headers={'Retry-After': {'description': 'Seconds to wait before retrying.',
                                     'schema': {'type': 'integer'}}},
        ),
        'ServerError': problem('Something failed on our side. Never contains internal detail.'),
    }


def _operations() -> dict:
    common = {'429': _response('TooManyRequests'), '500': _response('ServerError')}
    return {
        '/api/v1': {
            'get': {
                'tags': ['Service'], 'operationId': 'getIndex',
                'summary': 'What this API is, and where its endpoints are',
                'responses': {'200': _json(_ref('ApiIndex'), 'The API index.')},
            },
        },
        '/api/v1/health': {
            'get': {
                'tags': ['Service'], 'operationId': 'getHealth',
                'summary': 'Liveness and readiness',
                'description': 'Does not call the upstream weather service, so an outage there '
                               'cannot make the host restart this one. Not rate limited.',
                'responses': {
                    '200': _json(_ref('Health'), 'Running, airport database loaded.'),
                    '503': _json(_ref('Health'), 'Running, but the airport database failed to load.'),
                },
            },
        },
        '/api/v1/openapi.json': {
            'get': {
                'tags': ['Service'], 'operationId': 'getOpenApi',
                'summary': 'This document',
                'responses': {'200': _json({'type': 'object'}, 'An OpenAPI 3.1 description of the API.')},
            },
        },
        '/api/v1/airports': {
            'get': {
                'tags': ['Airports'], 'operationId': 'listAirports',
                'summary': 'Look up several airports at once',
                'parameters': [{
                    'name': 'codes', 'in': 'query', 'required': True,
                    'description': f'Comma-separated ICAO identifiers, at most {config.MAX_AIRPORT_CODES}.',
                    'schema': {'type': 'string', 'example': 'KJFK,EGLL,VIDP'},
                }],
                'responses': {
                    '200': _json(_ref('AirportBatch'), 'Every identifier asked for, known or not.'),
                    '400': _response('BadRequest'), **common,
                },
            },
        },
        '/api/v1/airports/{icao}': {
            'get': {
                'tags': ['Airports'], 'operationId': 'getAirport',
                'summary': 'One airport, with links to its alternates and pilot reports',
                'parameters': [ICAO_PATH_PARAM],
                'responses': {
                    '200': _json(_ref('AirportResource'), 'The airport.'),
                    '400': _response('BadRequest'), '404': _response('NotFound'), **common,
                },
            },
        },
        '/api/v1/airports/{icao}/alternates': {
            'get': {
                'tags': ['Airports'], 'operationId': 'listAlternates',
                'summary': 'Nearby airports usable as diversions, best conditions first',
                'parameters': [
                    ICAO_PATH_PARAM,
                    {'name': 'radius', 'in': 'query', 'description': 'Search radius, nautical miles. Clamped to 25-400.',
                     'schema': {'type': 'integer', 'default': 200, 'minimum': 25, 'maximum': 400}},
                    {'name': 'limit', 'in': 'query', 'description': 'Most alternates to return. Clamped to 1-20.',
                     'schema': {'type': 'integer', 'default': 8, 'minimum': 1, 'maximum': 20}},
                    {'name': 'runway', 'in': 'query',
                     'description': 'Runway heading in degrees, to compute crosswind components.',
                     'schema': {'type': 'number', 'minimum': 0, 'maximum': 360}},
                ],
                'responses': {
                    '200': _json(_ref('Alternates'), 'The alternates found.'),
                    '400': _response('BadRequest'), '404': _response('NotFound'), **common,
                },
            },
        },
        '/api/v1/airports/{icao}/pireps': {
            'get': {
                'tags': ['Airports'], 'operationId': 'listPilotReports',
                'summary': 'Pilot reports (PIREPs) filed near an airport',
                'parameters': [
                    ICAO_PATH_PARAM,
                    {'name': 'distance', 'in': 'query', 'description': 'Statute miles. Clamped to 10-500.',
                     'schema': {'type': 'integer', 'default': 150, 'minimum': 10, 'maximum': 500}},
                    {'name': 'age', 'in': 'query', 'description': 'Hours back to look. Clamped to 1-48.',
                     'schema': {'type': 'integer', 'default': 2, 'minimum': 1, 'maximum': 48}},
                    {'name': 'raw', 'in': 'query', 'description': 'true: original report text, no summaries.',
                     'schema': {'type': 'boolean', 'default': False}},
                ],
                'responses': {
                    '200': _json(_ref('PilotReports'), 'Reports, newest first.'),
                    '400': _response('BadRequest'), **common,
                },
            },
        },
        '/api/v1/briefings': {
            'post': {
                'tags': ['Briefings'], 'operationId': 'createBriefing',
                'summary': 'Brief a flight plan: route weather timeline, NOTAMs and risk',
                'description': 'Calls the upstream weather service about seven times, so it has its own, '
                               'tighter rate limit. The briefing is computed, not stored, so the response '
                               'is 200 with the briefing rather than 201 with a Location.',
                'requestBody': {'required': True,
                                'content': {'application/json': {'schema': _ref('FlightPlan')}}},
                'responses': {
                    '200': _json(_ref('Briefing'), 'The briefing.'),
                    '400': _response('BadRequest'), '413': _response('PayloadTooLarge'), **common,
                },
            },
        },
        '/api/v1/flight-plans/parse': {
            'post': {
                'tags': ['Briefings'], 'operationId': 'parseFlightPlan',
                'summary': 'Turn free text into a structured flight plan',
                'description': 'A controller resource — an action rather than a stored thing — so it is '
                               'named with a verb, and nothing is created.',
                'requestBody': {'required': True,
                                'content': {'application/json': {'schema': _ref('ParseRequest')}}},
                'responses': {
                    '200': _json(_ref('ParseResult'), 'What was understood.'),
                    '400': _response('BadRequest'), '413': _response('PayloadTooLarge'), **common,
                },
            },
        },
    }


# The original, unversioned addresses (routes/legacy_routes.py). Listed so the
# reference shows them struck through, each pointing at its replacement.
LEGACY = {
    '/api': ('/api/v1', 'get'),
    '/api/health': ('/api/v1/health', 'get'),
    '/api/airports': ('/api/v1/airports', 'get'),
    '/api/alternates/{icao}': ('/api/v1/airports/{icao}/alternates', 'get'),
    '/api/pirep-reports/{icao}': ('/api/v1/airports/{icao}/pireps', 'get'),
    '/api/enhanced-flight-plan': ('/api/v1/briefings', 'post'),
    '/api/process-natural-language': ('/api/v1/flight-plans/parse', 'post'),
}


def build_spec(version: str) -> dict:
    paths = _operations()

    for old, (successor, method) in LEGACY.items():
        current = paths[successor][method]
        paths[old] = {method: {
            **{k: v for k, v in current.items() if k not in ('operationId', 'summary', 'description')},
            'tags': ['Deprecated'],
            'operationId': current['operationId'] + 'Legacy',
            'summary': f'Deprecated — use {method.upper()} {successor}',
            'description': f'The original unversioned address for `{method.upper()} {successor}`, still '
                           'answered while clients move over. Responses carry `Deprecation`, `Sunset` and '
                           f'`Link: <{successor}>; rel="successor-version"` headers, and errors also include '
                           'the old `error` member.',
            'deprecated': True,
        }}

    return {
        'openapi': '3.1.0',
        'info': {
            'title': 'NavPort API',
            'version': version,
            'summary': 'Aviation weather and route risk briefings.',
            'description': (
                'A REST API over HTTPS. Responses are JSON; errors are '
                '[RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457) '
                '(`application/problem+json`). No authentication — the data is public — but every '
                'client IP has a rate limit, published by `GET /api/v1/health`; exceeding it returns '
                '429 with `Retry-After`. Weather comes from the Aviation Weather Center '
                '(aviationweather.gov); NOTAMs are simulated and labelled as such.'
            ),
            'license': {'name': 'MIT', 'identifier': 'MIT'},
        },
        # Relative, so the document is correct wherever it is served from: it
        # resolves against the address the document itself was fetched from.
        'servers': [{'url': '/', 'description': 'This deployment'}],
        'tags': [
            {'name': 'Briefings', 'description': 'Route briefings and flight-plan parsing.'},
            {'name': 'Airports', 'description': 'Airport identity, diversions and pilot reports.'},
            {'name': 'Service', 'description': 'The API describing itself.'},
            {'name': 'Deprecated', 'description': 'Original unversioned addresses, kept as aliases.'},
        ],
        'paths': paths,
        'components': {
            'schemas': _schemas(),
            'responses': _responses(),
        },
    }
