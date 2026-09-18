"""Application-wide configuration and shared constants.

Every default here is the *safe* one, so an unconfigured deployment is a
hardened deployment. Local development opts out explicitly (`run.bat` and
`run.command` set `NAVPORT_ENV=development`), which is the right way round:
forgetting to set a variable in production must never be what enables the
debugger.
"""

import os


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------

ENV = os.environ.get("NAVPORT_ENV", "production").strip().lower()
IS_PRODUCTION = ENV not in ("development", "dev", "local")

# Aviation Weather Center API (aviationweather.gov)
AVIATIONWEATHER_BASE_URL = "https://aviationweather.gov/api/data"

# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------

# Containers need 0.0.0.0 to be reachable from outside the container; a bare
# `python run.py` on a laptop should not expose itself to the whole network.
HOST = os.environ.get("NAVPORT_HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1")

# Azure Container Apps / App Service inject the port to listen on as $PORT.
PORT = _int("PORT", _int("NAVPORT_PORT", 5000))

# The Werkzeug debugger is a remote code execution primitive. It can only ever
# be switched on by explicitly running in development.
DEBUG = _flag("NAVPORT_DEBUG", False) and not IS_PRODUCTION

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------

# Browsers enforce same-origin on their own, so the web build needs no CORS at
# all. The native shells do: a Tauri or Capacitor webview has its own scheme,
# which counts as a foreign origin. Those get named here rather than allowing
# `*`, which would let any website on the internet drive this API with a
# visitor's IP and burn the shared upstream quota.
_DEFAULT_APP_ORIGINS = [
    "tauri://localhost",          # Tauri v2, macOS + iOS
    "http://tauri.localhost",     # Tauri v2, Windows
    "https://tauri.localhost",    # Tauri v2, Android
    "capacitor://localhost",      # Capacitor, iOS
    "http://localhost",           # Capacitor, Android
]

_extra_origins = [o.strip() for o in os.environ.get("NAVPORT_CORS_ORIGINS", "").split(",") if o.strip()]

# In development the dashboard is often opened from a phone on the LAN or from
# a `tauri dev` shell on a random port, so the allowlist is relaxed there only.
CORS_ORIGINS = _DEFAULT_APP_ORIGINS + _extra_origins if IS_PRODUCTION else "*"

# Largest request body we will even read, let alone parse.
MAX_CONTENT_LENGTH = _int("NAVPORT_MAX_BODY_BYTES", 64 * 1024)

# Token-bucket rate limit per client IP. The upstream Aviation Weather Center
# API is a free public service and one briefing fans out into seven calls, so
# an unthrottled endpoint here is a way to get the whole deployment blocked.
RATE_LIMIT_REQUESTS = _int("NAVPORT_RATE_LIMIT", 60)
RATE_LIMIT_WINDOW_SECONDS = _int("NAVPORT_RATE_WINDOW", 60)

# Briefings are the expensive endpoint; they get a tighter budget of their own.
BRIEFING_RATE_LIMIT = _int("NAVPORT_BRIEFING_RATE_LIMIT", 10)

# Only trust X-Forwarded-For when something we control is actually setting it.
# Azure Container Apps and App Service both terminate TLS at their ingress and
# set it; a directly-exposed server must not, or any client can spoof its IP
# and walk straight through the rate limiter.
TRUST_PROXY_HEADERS = _flag("NAVPORT_TRUST_PROXY", IS_PRODUCTION)

# Console telemetry is a development affordance: it prints ANSI art and holds
# every client IP and User-Agent in memory. Off in production.
TELEMETRY_ENABLED = _flag("NAVPORT_TELEMETRY", not IS_PRODUCTION)

# --------------------------------------------------------------------------
# Caching / efficiency
# --------------------------------------------------------------------------

# Airport coordinates are effectively static; weather is not.
CACHE_TTL_STATION_SECONDS = _int("NAVPORT_CACHE_STATION_TTL", 24 * 3600)
CACHE_TTL_WEATHER_SECONDS = _int("NAVPORT_CACHE_WEATHER_TTL", 300)
CACHE_MAX_ENTRIES = _int("NAVPORT_CACHE_MAX_ENTRIES", 512)

# Responses above this are worth compressing; below it, the CPU costs more
# than the bytes saved.
GZIP_MIN_BYTES = _int("NAVPORT_GZIP_MIN_BYTES", 1024)

# Ceiling on what we will buffer into memory to compress. Compressing a static
# file means reading it off the streaming path first, so this bounds how much
# one request can make a worker allocate.
GZIP_MAX_BYTES = _int("NAVPORT_GZIP_MAX_BYTES", 4 * 1024 * 1024)

# --------------------------------------------------------------------------
# Request limits
# --------------------------------------------------------------------------

MAX_WAYPOINTS = _int("NAVPORT_MAX_WAYPOINTS", 10)
MAX_AIRPORT_CODES = _int("NAVPORT_MAX_AIRPORT_CODES", 200)
MAX_TEXT_LENGTH = _int("NAVPORT_MAX_TEXT_LENGTH", 2000)

# --------------------------------------------------------------------------
# Domain constants
# --------------------------------------------------------------------------

# PIREP intensity code -> human readable label
INTENSITY_MAP = {
    "LGT": "Light",
    "MOD": "Moderate",
    "SEV": "Severe",
    "SVR": "Severe",
    "EXTM": "Extreme",
    "LGT-MOD": "Light to Moderate",
    "MOD-SEV": "Moderate to Severe",
    "NEG": "None",
    "OCNL": "Occasional",
    "CONS": "Continuous",
}

# Small lookup table for friendlier PIREP location descriptions
AIRPORT_LOOKUP = {
    "KJFK": "John F. Kennedy International Airport, New York",
    "KLAX": "Los Angeles International Airport",
    "KBOS": "Boston Logan International Airport",
    "KSEA": "Seattle-Tacoma International Airport",
    "KSFO": "San Francisco International Airport",
    "KORD": "Chicago O'Hare International Airport",
    "KDEN": "Denver International Airport",
    "KATL": "Hartsfield-Jackson Atlanta International Airport",
    "KDFW": "Dallas/Fort Worth International Airport",
    "KLAS": "McCarran International Airport, Las Vegas",
    "KMIA": "Miami International Airport",
    "KPHX": "Phoenix Sky Harbor International Airport",
}

# Departure time bounds enforced by the Aviation Weather Center API
MAX_FUTURE_DEPARTURE_HOURS = 4
MAX_PAST_DEPARTURE_DAYS = 15
