"""PIREP lookup endpoint used by the pilot-reports modal."""

import logging

from flask import Blueprint, jsonify, request

from backend.models.pirep import make_summary
from backend.services.pirep_service import PIREPService

pirep_bp = Blueprint('pirep', __name__, url_prefix='/api')
pirep_service = PIREPService(verbose=False)


@pirep_bp.route('/pirep-reports/<station_id>', methods=['GET'])
def get_pirep_reports(station_id):
    """Get PIREP reports for a specific station, either as plain-English
    summaries or the original raw report text (?raw=true)."""
    try:
        distance_mi = int(request.args.get('distance', 150))
        age_hours = int(request.args.get('age', 2))
        show_raw = request.args.get('raw', 'false').lower() == 'true'

        pireps = pirep_service.fetch_and_sort(
            station_id=station_id.upper(),
            distance_mi=distance_mi,
            age_hours=age_hours,
        )

        pirep_list = []
        for pirep in pireps:
            pirep_dict = {
                'raw': pirep.raw,
                'type': pirep.type,
                'obs_time': pirep.obs_time,
                'receipt_time': pirep.receipt_time,
                'lat': pirep.lat,
                'lon': pirep.lon,
                'altitude_ft_msl': pirep.altitude_ft_msl,
                'station': pirep.station,
                'turbulence': pirep.turbulence,
                'icing': pirep.icing,
                'sky': pirep.sky,
                'temp_c': pirep.temp_c,
                'aircraft': pirep.aircraft,
                'remarks': pirep.remarks,
            }

            if not show_raw:
                pirep_dict['summary'] = make_summary(pirep)

            pirep_list.append(pirep_dict)

        return jsonify({
            'station_id': station_id.upper(),
            'pireps': pirep_list,
            'count': len(pirep_list),
            'show_raw': show_raw,
        })

    except Exception as e:
        logging.error(f"Error fetching PIREP reports: {e}")
        return jsonify({'error': f'Failed to fetch PIREP reports: {str(e)}'}), 500
