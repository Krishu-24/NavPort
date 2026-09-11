"""Application-wide configuration and shared constants."""

import os

# Aviation Weather Center API (aviationweather.gov)
AVIATIONWEATHER_BASE_URL = "https://aviationweather.gov/api/data"

# Flask server
HOST = os.environ.get("NAVPORT_HOST", "0.0.0.0")
PORT = int(os.environ.get("NAVPORT_PORT", 5000))
DEBUG = os.environ.get("NAVPORT_DEBUG", "true").lower() == "true"

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
