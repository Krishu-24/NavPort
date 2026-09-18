"""Rebuild backend/data/airports.json.gz from the OurAirports dataset.

Run this to refresh the bundled airport database:

    python scripts/build_airport_db.py

Source: https://ourairports.com/data/airports.csv — public domain. Only
airports with a 4-character identifier are kept, since that is what aviation
weather reports are keyed by.

Each airport is indexed under every identifier it answers to (`icao_code`,
`gps_code`, `ident`), because US fields routinely report weather under an
identifier that isn't their formal ICAO code.

Values are stored positionally to keep the shipped file small:

    [name, iata, city, country, kind, elevation_ft, lat, lon]
"""

import csv
import gzip
import io
import json
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUTPUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "airports.json.gz"

# OurAirports `type` -> the single-letter code the app stores.
KIND_CODES = {
    'large_airport': 'L',
    'medium_airport': 'M',
    'small_airport': 'S',
    'seaplane_base': 'W',
}


def fetch() -> str:
    print(f"Downloading {SOURCE_URL} ...")
    request = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'NavPort-DB-Builder/1.0'})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    print(f"  {len(raw) / 1e6:.1f} MB")
    return raw.decode('utf-8')


def number(value, cast, default=None):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def build(csv_text: str) -> dict:
    airports = {}
    rows = 0

    for row in csv.DictReader(io.StringIO(csv_text)):
        rows += 1

        kind = KIND_CODES.get(row.get('type', ''))
        if kind is None:                      # heliports, balloonports, closed
            continue

        lat = number(row.get('latitude_deg'), float)
        lon = number(row.get('longitude_deg'), float)
        if lat is None or lon is None:
            continue

        record = [
            row.get('name', '').strip(),
            (row.get('iata_code') or '').strip().upper(),
            (row.get('municipality') or '').strip(),
            (row.get('iso_country') or '').strip().upper(),
            kind,
            number(row.get('elevation_ft'), int),
            round(lat, 5),
            round(lon, 5),
        ]

        # Every identifier this airport might report weather under.
        for field in ('icao_code', 'gps_code', 'ident'):
            code = (row.get(field) or '').strip().upper()
            # `icao_code` is the authoritative identifier, so it must not be
            # overwritten by another airport's `ident` colliding with it.
            if len(code) == 4 and code.isalnum() and (code not in airports or field == 'icao_code'):
                airports[code] = record

    print(f"  read {rows} rows, kept {len(airports)} identifiers")
    return airports


def main() -> int:
    airports = build(fetch())

    if len(airports) < 30_000:
        print(f"Refusing to write: only {len(airports)} identifiers, expected 30k+. "
              "The source format may have changed.", file=sys.stderr)
        return 1

    for required in ('KJFK', 'EGLL', 'VIDP', 'KLAX'):
        if required not in airports:
            print(f"Refusing to write: {required} is missing from the result.", file=sys.stderr)
            return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(airports, separators=(',', ':'), ensure_ascii=False)

    with gzip.open(OUTPUT, 'wt', encoding='utf-8', compresslevel=9) as handle:
        handle.write(payload)

    print(f"Wrote {OUTPUT} — {len(payload) / 1e6:.1f} MB JSON "
          f"-> {OUTPUT.stat().st_size / 1e6:.1f} MB gzipped")
    return 0


if __name__ == '__main__':
    sys.exit(main())
