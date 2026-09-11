"""FAA/NWS flight categories — the language pilots actually plan in.

Ceiling and visibility are evaluated independently and the *worse* of the two
decides the category:

    LIFR   ceiling  < 500 ft   or  visibility < 1 sm
    IFR    ceiling  < 1000 ft  or  visibility < 3 sm
    MVFR   ceiling <= 3000 ft  or  visibility <= 5 sm
    VFR    ceiling  > 3000 ft  and visibility > 5 sm

"Ceiling" is the lowest broken, overcast or vertical-visibility layer — few and
scattered layers are not a ceiling.
"""

import math
import re
from typing import Dict, List, Optional

# Ordered worst -> best, so max()/min() on the rank is meaningful.
CATEGORIES = ('LIFR', 'IFR', 'MVFR', 'VFR')
RANK = {name: i for i, name in enumerate(CATEGORIES)}

CEILING_COVERS = ('BKN', 'OVC', 'VV')

DESCRIPTIONS = {
    'VFR':  'Visual flight rules',
    'MVFR': 'Marginal visual flight rules',
    'IFR':  'Instrument flight rules',
    'LIFR': 'Low instrument flight rules',
}


def parse_visibility_sm(value) -> Optional[float]:
    """Normalise the several shapes the API reports visibility in, to statute miles."""
    if value is None or value == '':
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().upper()

    if text in ('CAVOK', 'SKC', 'CLR'):
        return 10.0

    # "10+", "6+SM"
    text = text.replace('SM', '').strip()
    if text.endswith('+'):
        text = text[:-1]

    # Fractions, including the mixed "1 1/2" form.
    if '/' in text:
        try:
            whole = 0.0
            parts = text.split()
            if len(parts) == 2:
                whole = float(parts[0])
                text = parts[1]
            num, den = text.split('/')
            return whole + float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None

    try:
        number = float(text)
    except ValueError:
        match = re.search(r'[\d.]+', text)
        if not match:
            return None
        number = float(match.group())

    # A bare 4-digit value is metres (e.g. 9999), not miles.
    if number > 100:
        return round(number / 1609.344, 1)

    return number


def ceiling_ft(clouds: Optional[List[Dict]]) -> Optional[int]:
    """Lowest broken/overcast/vertical-visibility layer, in feet AGL."""
    if not clouds:
        return None

    bases = []
    for layer in clouds:
        if not isinstance(layer, dict):
            continue
        if layer.get('cover') in CEILING_COVERS:
            base = layer.get('base')
            if base is None:
                # A vertical-visibility layer with no base is a zero ceiling.
                if layer.get('cover') == 'VV':
                    bases.append(0)
                continue
            try:
                bases.append(int(base))
            except (TypeError, ValueError):
                continue

    return min(bases) if bases else None


def flight_category(ceiling: Optional[int], visibility: Optional[float]) -> str:
    """Worst of the ceiling and visibility categories."""
    by_ceiling = 'VFR'
    if ceiling is not None:
        if ceiling < 500:
            by_ceiling = 'LIFR'
        elif ceiling < 1000:
            by_ceiling = 'IFR'
        elif ceiling <= 3000:
            by_ceiling = 'MVFR'

    by_visibility = 'VFR'
    if visibility is not None:
        if visibility < 1:
            by_visibility = 'LIFR'
        elif visibility < 3:
            by_visibility = 'IFR'
        elif visibility <= 5:
            by_visibility = 'MVFR'

    return by_ceiling if RANK[by_ceiling] <= RANK[by_visibility] else by_visibility


def categorise(observation: Dict) -> Dict:
    """Derive ceiling, visibility and flight category from a METAR-shaped dict."""
    ceiling = ceiling_ft(observation.get('clouds'))
    visibility = parse_visibility_sm(observation.get('visib'))
    category = flight_category(ceiling, visibility)

    return {
        'flight_category': category,
        'flight_category_label': DESCRIPTIONS[category],
        'ceiling_ft': ceiling,
        'visibility_sm': visibility,
    }


def worst(categories) -> str:
    """The most restrictive category in a sequence (VFR when empty)."""
    ranked = [RANK[c] for c in categories if c in RANK]
    return CATEGORIES[min(ranked)] if ranked else 'VFR'


def is_better(candidate: str, reference: str) -> bool:
    return RANK.get(candidate, -1) > RANK.get(reference, -1)


# ---------------------------------------------------------------------------
# Wind components — the other number a pilot checks before committing
# ---------------------------------------------------------------------------


def wind_components(wind_dir: Optional[float], wind_speed: Optional[float],
                    runway_heading: float) -> Optional[Dict]:
    """Headwind and crosswind for a runway, in knots.

    Positive headwind means a headwind; negative means a tailwind.
    `crosswind` is unsigned, `crosswind_from` says which side it pushes from.
    """
    if wind_dir is None or wind_speed is None:
        return None

    try:
        angle = math.radians(float(wind_dir) - float(runway_heading))
        speed = float(wind_speed)
    except (TypeError, ValueError):
        return None

    headwind = speed * math.cos(angle)
    crosswind = speed * math.sin(angle)

    return {
        'headwind': round(headwind),
        'crosswind': round(abs(crosswind)),
        'crosswind_from': 'right' if crosswind > 0 else 'left',
        'is_tailwind': headwind < 0,
    }


# ---------------------------------------------------------------------------
# Density altitude — a standard element of an FAA preflight briefing, and the
# number that decides whether the aircraft will actually perform today
# ---------------------------------------------------------------------------

HPA_PER_INHG = 33.8639
FT_PER_M = 3.28084
STANDARD_INHG = 29.92


def density_altitude(temp_c: Optional[float], altimeter_hpa: Optional[float],
                     elevation_m: Optional[float]) -> Optional[Dict]:
    """Pressure and density altitude in feet.

    The weather API reports altimeter in hectopascals and field elevation in
    metres, so both are converted before the standard formulas are applied.
    """
    if temp_c is None or altimeter_hpa is None or elevation_m is None:
        return None

    try:
        temp = float(temp_c)
        altimeter_inhg = float(altimeter_hpa) / HPA_PER_INHG
        elevation_ft = float(elevation_m) * FT_PER_M
    except (TypeError, ValueError, ZeroDivisionError):
        return None

    pressure_alt = (STANDARD_INHG - altimeter_inhg) * 1000 + elevation_ft
    isa_temp = 15.0 - 2.0 * (pressure_alt / 1000.0)
    density_alt = pressure_alt + 120.0 * (temp - isa_temp)

    return {
        'field_elevation_ft': round(elevation_ft),
        'pressure_altitude_ft': round(pressure_alt),
        'density_altitude_ft': round(density_alt),
        'isa_deviation_c': round(temp - isa_temp, 1),
        # Rule of thumb pilots use: >2000 ft above field elevation is worth a
        # performance check before departure.
        'significant': (density_alt - elevation_ft) > 2000,
    }


def bearing_between(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Initial great-circle bearing in degrees true, 1-360."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)

    degrees = (math.degrees(math.atan2(y, x)) + 360) % 360
    return int(round(degrees)) or 360


def compass_point(bearing: float) -> str:
    points = ('N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
              'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW')
    return points[int((bearing % 360) / 22.5 + 0.5) % 16]
