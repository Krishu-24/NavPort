"""Flight plan analysis endpoints: natural-language extraction and the
comprehensive weather/NOTAM/risk timeline.

Validation happens at the top of each handler and raises `BadRequest`, which
the app-level error handler turns into a 400. Anything that escapes is a bug
in our code, not bad input, so it becomes an opaque 500 and a logged
traceback — never an exception string echoed back to the caller.
"""

import logging

from flask import Blueprint, jsonify, request

from backend import validation
from backend.services import airports, flight_rules
from backend.services.weather_service import WeatherProcessor

log = logging.getLogger(__name__)

flight_bp = Blueprint('flight', __name__, url_prefix='/api')
weather_processor = WeatherProcessor()


@flight_bp.route('/airports', methods=['GET'])
def airport_lookup():
    """Resolve identifiers to IATA codes and names: ?codes=KJFK,EGLL"""
    codes = validation.codes_param(request.args.get('codes', ''))

    response = jsonify({'airports': airports.describe_many(codes), 'known': airports.count()})
    # The bundled airport database only changes when the app is redeployed.
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@flight_bp.route('/alternates/<icao>', methods=['GET'])
def alternates(icao):
    """Nearby airports reporting better conditions — diversion planning."""
    station = validation.icao(icao, 'airport code')
    radius = validation.integer(request.args.get('radius'), 'radius', default=200, minimum=25, maximum=400)
    limit = validation.integer(request.args.get('limit'), 'limit', default=8, minimum=1, maximum=20)
    runway_heading = validation.number(request.args.get('runway'), 'runway', minimum=0, maximum=360)

    result = weather_processor.find_alternates(
        station, radius_nm=radius, limit=limit, runway_heading=runway_heading)

    if 'error' in result:
        return jsonify(result), 404

    return jsonify(result)


@flight_bp.route('/process-natural-language', methods=['POST'])
def process_natural_language():
    """Process natural language flight plan input."""
    body = validation.json_body(request)
    text = validation.text_field(body, 'text')

    flight_plan = weather_processor.nlp_processor.extract_flight_plan_from_text(text)

    return jsonify({
        'flight_plan': flight_plan,
        'original_text': text,
        'success': True,
    })


@flight_bp.route('/enhanced-flight-plan', methods=['POST'])
def enhanced_flight_plan():
    """Enhanced flight plan analysis with comprehensive weather timeline, NOTAMs, and NLP."""
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
