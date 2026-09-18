"""PIREP lookup endpoint used by the pilot-reports modal."""

import logging

from flask import Blueprint, jsonify, request

from backend import validation
from backend.models.pirep import make_summary
from backend.services.pirep_service import PIREPService

log = logging.getLogger(__name__)

pirep_bp = Blueprint('pirep', __name__, url_prefix='/api')
pirep_service = PIREPService(verbose=False)


@pirep_bp.route('/pirep-reports/<station_id>', methods=['GET'])
def get_pirep_reports(station_id):
    """Get PIREP reports for a specific station, either as plain-English
    summaries or the original raw report text (?raw=true)."""
    station = validation.icao(station_id, 'station id')
    distance_mi = validation.integer(
        request.args.get('distance'), 'distance', default=150, minimum=10, maximum=500)
    age_hours = validation.integer(
        request.args.get('age'), 'age', default=2, minimum=1, maximum=48)
    show_raw = request.args.get('raw', 'false').lower() == 'true'

    pireps = pirep_service.fetch_and_sort(
        station_id=station,
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
        'station_id': station,
        'pireps': pirep_list,
        'count': len(pirep_list),
        'show_raw': show_raw,
    })
