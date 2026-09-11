"""Flight plan analysis endpoints: natural-language extraction and the
comprehensive weather/NOTAM/risk timeline."""

import logging

from flask import Blueprint, jsonify, request

from backend.services.weather_service import WeatherProcessor

flight_bp = Blueprint('flight', __name__, url_prefix='/api')
weather_processor = WeatherProcessor()


@flight_bp.route('/process-natural-language', methods=['POST'])
def process_natural_language():
    """Process natural language flight plan input."""
    try:
        data = request.get_json()
        text = data.get('text', '')

        if not text:
            return jsonify({'error': 'No text provided'}), 400

        flight_plan = weather_processor.nlp_processor.extract_flight_plan_from_text(text)

        return jsonify({
            'flight_plan': flight_plan,
            'original_text': text,
            'success': True,
        })

    except Exception as e:
        logging.error(f"Error processing natural language: {e}")
        return jsonify({'error': f'Processing error: {str(e)}'}), 500


@flight_bp.route('/enhanced-flight-plan', methods=['POST'])
def enhanced_flight_plan():
    """Enhanced flight plan analysis with comprehensive weather timeline, NOTAMs, and NLP."""
    try:
        data = request.get_json()
        departure = data.get('departure', '').upper()
        destination = data.get('destination', '').upper()
        waypoints = [wp.strip().upper() for wp in data.get('waypoints', []) if wp.strip()]
        cruise_speed = int(data.get('cruise_speed', 450))
        departure_time = data.get('departure_time')

        logging.info(f"Received request: departure={departure}, destination={destination}, departure_time={departure_time}")

        if not departure or not destination:
            return jsonify({'error': 'Departure and destination required'}), 400

        try:
            flight_segments = weather_processor.calculate_flight_path(
                departure, destination, waypoints, cruise_speed, departure_time
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400

        if not flight_segments:
            return jsonify({'error': 'Unable to calculate flight path'}), 400

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
            'nlp_briefing_summary': weather_briefing_summary,
            'risk_assessment': risk_assessment,
        })

    except Exception as e:
        logging.error(f"Error in enhanced flight plan: {e}")
        return jsonify({'error': f'Processing error: {str(e)}'}), 500
