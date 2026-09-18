"""Request validation.

Two jobs. The obvious one is returning 400 instead of 500 when a client sends
nonsense. The less obvious one matters more: every identifier here is
interpolated into an outbound request to aviationweather.gov, so an
unvalidated identifier is our query string in someone else's hands. Rejecting
anything that isn't four letters or digits closes that off at the door.
"""

import re

from backend.config import MAX_AIRPORT_CODES, MAX_TEXT_LENGTH, MAX_WAYPOINTS

# ICAO location indicators are exactly four alphanumerics. Some US fields use a
# digit (K12N), so this is not letters-only.
ICAO_RE = re.compile(r'^[A-Z0-9]{4}$')


class BadRequest(Exception):
    """Raised for client error; the message is safe to return verbatim."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def icao(value, field: str = 'airport code') -> str:
    """Normalise and validate a single identifier."""
    if not isinstance(value, str):
        raise BadRequest(f'{field} must be a 4-character ICAO code')

    code = value.strip().upper()
    if not ICAO_RE.match(code):
        raise BadRequest(f'{field} must be a 4-character ICAO code, e.g. KJFK — got {value.strip()[:16]!r}')
    return code


def icao_list(value, field: str = 'waypoints') -> list:
    """Validate a list of identifiers, dropping blanks."""
    if value in (None, ''):
        return []
    if not isinstance(value, list):
        raise BadRequest(f'{field} must be a list of ICAO codes')
    if len(value) > MAX_WAYPOINTS:
        raise BadRequest(f'At most {MAX_WAYPOINTS} {field} per request')

    return [icao(item, field) for item in value if str(item).strip()]


def codes_param(raw: str) -> list:
    """Parse and validate the `?codes=KJFK,EGLL` query parameter."""
    codes = [c for c in raw.replace(' ', '').upper().split(',') if c]
    if not codes:
        raise BadRequest('Pass ?codes=KJFK,EGLL')
    if len(codes) > MAX_AIRPORT_CODES:
        raise BadRequest(f'At most {MAX_AIRPORT_CODES} codes per request')

    return [icao(code) for code in codes]


def integer(value, field: str, *, default: int, minimum: int, maximum: int) -> int:
    """Clamp a numeric parameter, rejecting values that aren't numbers at all.

    Clamping rather than rejecting out-of-range values keeps a slightly-too-big
    `?radius=` working instead of failing the panel, but a non-numeric value is
    a caller bug and is reported as one.
    """
    if value in (None, ''):
        return default
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        # `from None` deliberately: the underlying ValueError's message
        # ("invalid literal for int() with base 10: ...") quotes the caller's
        # raw input, and chaining it would file that in the log as an internal
        # fault rather than ordinary bad input.
        raise BadRequest(f'{field} must be a number') from None

    return max(minimum, min(maximum, number))


def number(value, field: str, *, minimum: float, maximum: float):
    """Optional float parameter; None when absent."""
    if value in (None, ''):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise BadRequest(f'{field} must be a number') from None

    if not minimum <= parsed <= maximum:
        raise BadRequest(f'{field} must be between {minimum:g} and {maximum:g}')
    return parsed


def json_body(request) -> dict:
    """The parsed JSON object, or a 400 explaining what was wrong with it.

    `request.get_json(silent=True)` returns None both for a missing body and
    for malformed JSON, and returns a non-dict for a valid JSON scalar — all
    three reach `.get()` and raise AttributeError without this.
    """
    body = request.get_json(silent=True)
    if body is None:
        raise BadRequest('Request body must be JSON with a Content-Type of application/json')
    if not isinstance(body, dict):
        raise BadRequest('Request body must be a JSON object')
    return body


def text_field(body: dict, field: str = 'text') -> str:
    """A required free-text field, length-capped so a huge payload can't be
    turned into CPU time in the regex engine."""
    value = body.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BadRequest(f'No {field} provided')
    if len(value) > MAX_TEXT_LENGTH:
        raise BadRequest(f'{field} must be at most {MAX_TEXT_LENGTH} characters')
    return value.strip()


def departure_time(value) -> str:
    """The departure timestamp is parsed downstream; only shape is checked here."""
    if value in (None, ''):
        return None
    if not isinstance(value, str):
        raise BadRequest('departure_time must be an ISO-8601 string')
    if len(value) > 40:
        raise BadRequest('departure_time is not a valid timestamp')
    return value.strip()
