"""Airports, briefings and flight-plan parsing.

    GET  /api/v1/airports?codes=KJFK,EGLL      several airports at once
    GET  /api/v1/airports/{icao}               one airport
    GET  /api/v1/airports/{icao}/alternates    diversion options near it
    POST /api/v1/briefings                     a route briefing for a flight plan
    POST /api/v1/flight-plans/parse            free text -> a structured flight plan

Validation happens at the top of each handler and raises `BadRequest`, which
the app-level error handler turns into a Problem Details response (see
problems.py). Anything that escapes is a bug in our code, not bad input, so it
becomes an opaque 500 and a logged traceback — never an exception string
echoed back to the caller.
"""

import logging

from flask import jsonify, request, url_for

from navport import validation
from navport.routes import api_v1
from navport.services import airports, flight_rules
from navport.services.weather_service import WeatherProcessor

log = logging.getLogger(__name__)

weather_processor = WeatherProcessor()


@api_v1.route('/airports', methods=['GET'])
def list_airports():
    """Resolve identifiers to IATA codes and names: ?codes=KJFK,EGLL

    A filtered view of the airport collection. Unknown identifiers are still
    returned (with null fields) rather than dropped, so a client can tell
    "unknown" apart from "not asked for".
    """
    codes = validation.codes_param(request.args.get('codes', ''))

    response = jsonify({'airports': airports.describe_many(codes), 'known': airports.count()})
    # The bundled airport database only changes when the app is redeployed.
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@api_v1.route('/airports/<icao>', methods=['GET'])
def get_airport(icao):
    """One airport, with links to the resources that belong to it."""
    code = validation.icao(icao, 'airport code')
    found = airports.lookup(code)
    if not found:
        raise validation.BadRequest(f'No airport with identifier {code} in the database', status=404)

    position = airports.coordinates(code) or {}
    response = jsonify({
        **found,
        'lat': position.get('lat'),
        'lon': position.get('lon'),
        # Hypermedia: what a client can do next, so it needn't build these
        # URLs itself.
        'links': {
            'self': url_for('v1.get_airport', icao=code),
            'alternates': url_for('v1.list_alternates', icao=code),
            'pilot_reports': url_for('v1.list_pireps', icao=code),
        },
    })
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@api_v1.route('/airports/<icao>/alternates', methods=['GET'])
def list_alternates(icao):
    """Nearby airports reporting better conditions — diversion planning."""
    station = validation.icao(icao, 'airport code')
    radius = validation.integer(request.args.get('radius'), 'radius', default=200, minimum=25, maximum=400)
    limit = validation.integer(request.args.get('limit'), 'limit', default=8, minimum=1, maximum=20)
    runway_heading = validation.number(request.args.get('runway'), 'runway', minimum=0, maximum=360)

    result = weather_processor.find_alternates(
        station, radius_nm=radius, limit=limit, runway_heading=runway_heading)

    if 'error' in result:
        raise validation.BadRequest(result['error'], status=404)

    return jsonify(result)


@api_v1.route('/flight-plans/parse', methods=['POST'])
def parse_flight_plan():
    """Turn free text ("KJFK to KLAX via KORD at 450 knots") into a flight plan.

    A controller resource: parsing is an action, not a thing that gets stored,
    so it is named as one rather than disguised as a collection. Nothing is
    created, hence 200 rather than 201.
    """
    body = validation.json_body(request)
    text = validation.text_field(body, 'text')

    flight_plan = weather_processor.nlp_processor.extract_flight_plan_from_text(text)

    return jsonify({
        'flight_plan': flight_plan,
        'original_text': text,
        'success': True,
    })


@api_v1.route('/briefings', methods=['POST'])
def create_briefing():
    """A route briefing for a flight plan: timeline, NOTAMs, risk, summary.

    POST rather than GET because the input is a structured document (a route
    with waypoints, a time and a speed) and GET has no body. The briefing is
    computed and returned, not stored — there is no URL at which it would go
    on existing — so the response is 200 with the briefing, not 201 Created
    with a Location.
    """
    body = validation.json_body(request)

    departure = validation.icao(body.get('departure'), 'departure')
    destination = validation.icao(body.get('destination'), 'destination')
    waypoints = validation.icao_list(body.get('waypoints'), 'waypoints')
    cruise_speed = validation.integer(
        body.get('cruise_speed'), 'cruise_speed', default=450, minimum=40, maximum=900)
    departure_time = validation.departure_time(body.get('departure_time'))

    log.info("Briefing requested: %s -> %s via %s at %s",
             departure, destination, waypoints or '-', departure_time or 'now')

    # `calculate_flight_path` raises ValueError for departure times outside the
    # window the upstream API can answer for — a caller error, so 400.
    try:
        flight_segments = weather_processor.calculate_flight_path(
            departure, destination, waypoints, cruise_speed, departure_time
        )
    except ValueError as exc:
        # These ValueErrors are raised by us, with messages written for the
        # user ("Departure time cannot be more than 4 hours in the future"),
        # so passing the text through is intended.
        raise validation.BadRequest(str(exc)) from exc

    if not flight_segments:
        raise validation.BadRequest(
            'Could not resolve enough of this route to build a briefing. '
            'Check that each identifier is a real ICAO code with a reporting station.'
        )

    actual_departure_time = flight_segments[0]['start_time']
    all_airports = [departure, destination] + waypoints

    weather_data = weather_processor.get_comprehensive_weather(
        flight_segments=flight_segments,
        airports=all_airports,
        departure_time=actual_departure_time,
    )

    timeline = weather_processor.create_timeline_analysis(flight_segments, weather_data)

    severities = [item['severity'] for item in timeline]
    overall_severity = 'Clear'
    if 'Severe' in severities:
        overall_severity = 'Severe'
    elif 'Significant' in severities:
        overall_severity = 'Significant'

    # Worst flight category anywhere on the route, plus a per-category count
    # so the UI can say "3 intervals IFR or below".
    categories = [item.get('flight_category', 'VFR') for item in timeline]
    worst_category = flight_rules.worst(categories)
    category_counts = {name: categories.count(name) for name in flight_rules.CATEGORIES}
    below_vfr = sum(count for name, count in category_counts.items() if name != 'VFR')

    # Identity for every code the briefing mentions, so the UI can show
    # names and IATA codes without a second round trip per station.
    mentioned = {departure, destination, *waypoints}
    mentioned.update(
        item['conditions'].get('nearest_station')
        for item in timeline
        if item['conditions'].get('nearest_station') not in (None, 'Unknown')
    )
    mentioned.update(n.get('airport') for n in weather_data.get('notams', []) if n.get('airport'))
    identities = airports.describe_many([c for c in mentioned if c])

    airfields = weather_processor.airfield_reports([departure, destination])

    weather_briefing_summary = weather_processor.nlp_processor.summarize_weather_briefing(weather_data)
    risk_assessment = weather_processor.nlp_processor.generate_risk_assessment(timeline)

    return jsonify({
        'route': {
            'departure': departure,
            'destination': destination,
            'waypoints': waypoints,
            'cruise_speed': cruise_speed,
            'total_distance': sum(s['distance_nm'] for s in flight_segments),
            'total_flight_time': sum(s['flight_time_hours'] for s in flight_segments),
            'overall_severity': overall_severity,
            'flight_category': worst_category,
            'category_counts': category_counts,
            'intervals_below_vfr': below_vfr,
            'risk_assessment': risk_assessment,
        },
        'flight_segments': [{
            'from': s['from'],
            'to': s['to'],
            'distance_nm': s['distance_nm'],
            'flight_time_hours': s['flight_time_hours'],
            'start_time': s['start_time'].isoformat(),
            'end_time': s['end_time'].isoformat(),
        } for s in flight_segments],
        'timeline': timeline,
        'weather_summary': {
            'metars_count': len(weather_data.get('metars', [])),
            'tafs_count': len(weather_data.get('tafs', [])),
            'pireps_count': len(weather_data.get('pireps', [])),
            'sigmets_count': len(weather_data.get('sigmets', [])),
            'gairmets_count': len(weather_data.get('gairmets', [])),
            'cwas_count': len(weather_data.get('cwas', [])),
            'notams_count': len(weather_data.get('notams', [])),
        },
        'notams': weather_data.get('notams', []),
        'airports': identities,
        'airfields': airfields,
        'nlp_briefing_summary': weather_briefing_summary,
        'risk_assessment': risk_assessment,
    })
