"""Fetching and parsing of PIREPs (pilot reports) from the Aviation Weather Center API."""

import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from backend.config import AVIATIONWEATHER_BASE_URL
from backend.models.pirep import PIREP, parse_raw


def _first(*keys: str):
    def pick(d: Dict, default=None):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return default
    return pick


_pick_raw = _first("rawOb", "rawText", "raw", "report")
_pick_obs_time = _first("obsTime", "observationTime", "observation_time", "timeObs", "TM")
_pick_receipt_time = _first("receiptTime", "receipt_time")
_pick_lat = _first("lat", "latitude")
_pick_lon = _first("lon", "longitude")
_pick_alt_ft = _first("altitude_ft_msl", "altitudeFtMsl", "altitude_ft", "altitudeFt", "altitude", "FL")
_pick_station = _first("station", "stationId", "icaoId", "airport", "id", "location")
_pick_type = _first("type", "reportType")


class PIREPService:
    """Fetches PIREPs for a station and parses them into structured reports."""

    def __init__(self, base_url: str = AVIATIONWEATHER_BASE_URL, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NavPort-PIREPService/1.0"})
        self.verbose = verbose

    def _log(self, *args):
        if self.verbose:
            print(*args, file=sys.stderr)

    def fetch(self, *, station_id: str, distance_mi: int = 150, age_hours: int = 2, fmt: str = "json") -> List[Dict]:
        url = f"{self.base_url}/pirep"
        params = {"format": fmt, "age": age_hours, "id": station_id, "distance": distance_mi}
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 204:
                return []
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("reports", "data", "pireps", "items"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                return [data]
            return []
        except Exception as e:
            self._log(f"[WARN] PIREP request failed: {e}")
            return []

    def parse_api_json(self, items: List[Dict]) -> List[PIREP]:
        pireps: List[PIREP] = []
        for it in items:
            p = PIREP(
                raw=_pick_raw(it, ""),
                type=_pick_type(it),
                obs_time=_pick_obs_time(it),
                receipt_time=_pick_receipt_time(it),
                lat=_pick_lat(it),
                lon=_pick_lon(it),
                altitude_ft_msl=_pick_alt_ft(it),
                station=_pick_station(it),
            )
            pireps.append(parse_raw(p.raw or "", base=p))
        return pireps

    def fetch_and_sort(self, *, station_id: str, distance_mi: int = 150, age_hours: int = 2) -> List[PIREP]:
        items = self.fetch(station_id=station_id, distance_mi=distance_mi, age_hours=age_hours)
        if not items:
            return []
        pireps = self.parse_api_json(items)

        def sort_key(p: PIREP):
            time_str = p.obs_time or p.receipt_time
            try:
                if str(time_str).isdigit():
                    return datetime.fromtimestamp(int(time_str), tz=timezone.utc)
                return datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
            except Exception:
                return datetime.min

        return sorted(pireps, key=sort_key, reverse=True)
