"""PIREP (Pilot Report) data model and raw-text parsing."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from backend.config import AIRPORT_LOOKUP, INTENSITY_MAP


@dataclass
class PIREP:
    raw: str
    type: Optional[str] = None
    obs_time: Optional[str] = None
    receipt_time: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    altitude_ft_msl: Optional[int] = None
    station: Optional[str] = None
    turbulence: Optional[str] = None
    icing: Optional[str] = None
    sky: Optional[str] = None
    temp_c: Optional[float] = None
    aircraft: Optional[str] = None
    remarks: Optional[str] = None


# --- Raw PIREP text field regexes -------------------------------------------------
FL_RE = re.compile(r"/FL(\d+)")
TB_RE = re.compile(r"/TB\s*([^/]+)")
IC_RE = re.compile(r"/IC\s*([^/]+)")
SK_RE = re.compile(r"/SK\s*([^/]+)")
TA_RE = re.compile(r"/TA\s*([-+]?\d+)")
TP_RE = re.compile(r"/TP\s*([A-Z0-9]+)")
RM_RE = re.compile(r"/RM\s*([^/]+)")

CLOUD_RE = re.compile(r"(FEW|SCT|BKN|OVC)(\d{2,3})?(CB|TCU)?", re.IGNORECASE)
CLOUD_WORD = {"FEW": "few", "SCT": "scattered", "BKN": "broken", "OVC": "overcast"}
CLOUD_TYPE = {"CB": "cumulonimbus", "TCU": "towering cumulus"}


def severity_icon(level: str) -> str:
    if not level:
        return ""
    if "Light" in level:
        return "✅"
    if "Moderate" in level:
        return "⚠️"
    if "Severe" in level or "Extreme" in level:
        return "\U0001f534"
    return ""


def parse_raw(raw: str, base: Optional[PIREP] = None) -> PIREP:
    """Populate a PIREP's structured fields by parsing its raw report text."""
    p = base or PIREP(raw=raw)
    if m := FL_RE.search(raw):
        p.altitude_ft_msl = int(m.group(1)) * 100
    if m := TB_RE.search(raw):
        tb_val = m.group(1).strip()
        p.turbulence = INTENSITY_MAP.get(tb_val, tb_val)
    if m := IC_RE.search(raw):
        ic_val = m.group(1).strip()
        p.icing = INTENSITY_MAP.get(ic_val, ic_val)
    if m := SK_RE.search(raw):
        p.sky = m.group(1).strip()
    if m := TA_RE.search(raw):
        try:
            p.temp_c = float(m.group(1))
        except ValueError:
            pass
    if m := TP_RE.search(raw):
        p.aircraft = m.group(1)
    if m := RM_RE.search(raw):
        p.remarks = m.group(1).strip()
    return p


def _format_clouds(sky: str) -> Optional[str]:
    if not sky:
        return None
    up = sky.upper()
    if "CLR" in up or "SKC" in up:
        return "clear skies"
    phrases = []
    for m in CLOUD_RE.finditer(up):
        layer, hgt, conv = m.groups()
        layer_word = CLOUD_WORD.get(layer, layer.lower())
        add = f" {CLOUD_TYPE.get(conv, conv.lower())}" if conv else ""
        if hgt:
            try:
                feet = int(hgt) * 100
                phrases.append(f"{layer_word}{add} at {feet} ft")
            except ValueError:
                phrases.append(f"{layer_word}{add}")
        else:
            phrases.append(f"{layer_word}{add}")
    return ", ".join(phrases) if phrases else sky.lower()


def relative_time(timestr: Optional[str]) -> str:
    if not timestr:
        return "time unknown"
    if str(timestr).isdigit():
        try:
            t = datetime.fromtimestamp(int(timestr), tz=timezone.utc)
        except Exception:
            return f"reported at {timestr}"
    else:
        try:
            t = datetime.fromisoformat(str(timestr).replace("Z", "+00:00"))
        except Exception:
            return f"reported at {timestr}"

    now = datetime.now(timezone.utc)
    delta = now - t
    mins = int(delta.total_seconds() // 60)

    if mins < 1:
        return "observed just now"
    if mins < 60:
        return f"observed {mins} minutes ago"
    hours, mins = divmod(mins, 60)
    return f"observed {hours}h {mins}m ago"


def make_summary(p: PIREP) -> str:
    """Build a plain-English summary of a parsed PIREP."""
    parts = []
    if p.turbulence:
        parts.append(f"{severity_icon(p.turbulence)} {p.turbulence} turbulence reported")
    if p.icing:
        parts.append(f"{severity_icon(p.icing)} {p.icing} icing observed")
    clouds = _format_clouds(p.sky or "")
    if clouds:
        parts.append(clouds)
    if p.temp_c is not None:
        temp_str = f"{p.temp_c:.0f}" if float(p.temp_c).is_integer() else f"{p.temp_c}"
        parts.append(f"temperature {temp_str} degrees Celsius")
    if p.aircraft:
        parts.append(f"aircraft type {p.aircraft}")
    if p.remarks:
        parts.append(f"remarks {p.remarks}")
    alt = f"{p.altitude_ft_msl} ft" if p.altitude_ft_msl else "altitude not given"
    loc = AIRPORT_LOOKUP.get(p.station, f"near {p.station}") if p.station else "location unknown"
    time_info = relative_time(p.obs_time or p.receipt_time)
    return " | ".join(str(x) for x in (parts + [alt, loc, time_info]))
