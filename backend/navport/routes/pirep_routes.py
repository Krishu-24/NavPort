"""Pilot reports near an airport, used by the pilot-reports panel.

    GET /api/v1/airports/{icao}/pireps?distance=150&age=2&raw=false
"""

import logging

from flask import jsonify, request

from navport import validation
from navport.models.pirep import make_summary
from navport.routes import api_v1
from navport.services.pirep_service import PIREPService

log = logging.getLogger(__name__)

pirep_service = PIREPService(verbose=False)


@api_v1.route('/airports/<icao>/pireps', methods=['GET'])
def list_pireps(icao):
    """PIREPs reported near an airport, as plain-English summaries or the
    original raw report text (?raw=true). A sub-collection of the airport:
    the reports belong to the place they were filed around."""
    station = validation.icao(icao, 'airport code')
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
