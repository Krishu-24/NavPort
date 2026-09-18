"""Worldwide airport identity: ICAO -> IATA, name, city, country, elevation.

Data: OurAirports (https://ourairports.com/data/), public domain, trimmed to
airports with a 4-character identifier. Indexed by every identifier an airport
answers to — `icao_code`, `gps_code` and `ident` — because US fields routinely
report weather under an identifier that isn't their formal ICAO code
(K12N and KVES, for example, only resolve via the latter two).

Loaded once into memory at import; lookups are a dict hit.
"""

import gzip
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Shipped gzipped: 2.0 MB of JSON compresses to 0.6 MB, and it is read once at
# import, so the decompression cost is paid a single time at startup.
DATA_FILE = Path(__file__).resolve().parent.parent / 'data' / 'airports.json.gz'

# Stored positionally to keep the bundled file small.
# Regenerate with `python scripts/build_airport_db.py` if this layout changes.
_NAME, _IATA, _CITY, _COUNTRY, _KIND, _ELEV, _LAT, _LON = range(8)

KIND_LABELS = {
    'L': 'Large airport',
    'M': 'Medium airport',
    'S': 'Small airport',
    'W': 'Seaplane base',
}


def _load() -> Dict[str, list]:
    try:
        with gzip.open(DATA_FILE, 'rt', encoding='utf-8') as handle:
            return json.load(handle)
    except FileNotFoundError:
        logging.warning("Airport database missing at %s — codes will show unresolved.", DATA_FILE)
        return {}
    except (OSError, ValueError) as exc:
        logging.error("Could not read the airport database: %s", exc)
        return {}


_AIRPORTS = _load()


def count() -> int:
    return len(_AIRPORTS)


def lookup(code: Optional[str]) -> Optional[Dict]:
    """Resolve an identifier to an airport record, or None when unknown."""
    if not code:
        return None

    row = _AIRPORTS.get(str(code).strip().upper())
    if not row:
        return None

    return {
        'icao': str(code).strip().upper(),
        'iata': row[_IATA] or None,
        'name': row[_NAME],
        'city': row[_CITY] or None,
        'country': row[_COUNTRY] or None,
        'kind': KIND_LABELS.get(row[_KIND], 'Airport'),
        'elevation_ft': row[_ELEV],
    }


def coordinates(code: Optional[str]) -> Optional[Dict]:
    """Position of an airport, or None when the identifier is unknown.

    This is what lets a briefing be planned without a network round trip per
    airport: the bundled database already knows where everything is, so
    `stationinfo` is only consulted for identifiers it doesn't carry.
    """
    if not code:
        return None

    row = _AIRPORTS.get(str(code).strip().upper())
    if not row or len(row) <= _LON:
        return None

    return {
        'lat': row[_LAT],
        'lon': row[_LON],
        'name': row[_NAME],
    }


def describe(code: Optional[str]) -> Dict:
    """Always returns something renderable, even for an unknown identifier."""
    found = lookup(code)
    if found:
        return found

    return {
        'icao': (code or '').upper() or None,
        'iata': None,
        'name': None,
        'city': None,
        'country': None,
        'kind': None,
        'elevation_ft': None,
    }


def describe_many(codes: List[str]) -> Dict[str, Dict]:
    """Batch lookup, keyed by the identifier as given."""
    unique = {str(c).strip().upper() for c in codes if c}
    return {code: describe(code) for code in sorted(unique)}


def label(code: Optional[str]) -> str:
    """One-line human form: 'KJFK / JFK — John F. Kennedy International Airport'."""
    found = lookup(code)
    if not found:
        return (code or '').upper()

    ident = f"{found['icao']} / {found['iata']}" if found['iata'] else found['icao']
    return f"{ident} — {found['name']}"
