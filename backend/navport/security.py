"""Security middleware: response headers, per-IP rate limiting, error hygiene.

Written against the stdlib rather than pulling in flask-limiter and
flask-talisman, to keep the dependency list short enough to audit by reading
it. The trade-off is stated in `limiter` below: this is in-process state, so
it throttles per worker, not per deployment.
"""

import gzip
import io
import logging
import time
from collections import OrderedDict, deque
from threading import Lock

from flask import jsonify, request

from navport.config import (
    BRIEFING_RATE_LIMIT,
    GZIP_MAX_BYTES,
    GZIP_MIN_BYTES,
    IS_PRODUCTION,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    TRUST_PROXY_HEADERS,
)
from navport.validation import BadRequest

log = logging.getLogger(__name__)

# Text-shaped media types only. Compressing an already-compressed payload
# spends CPU to make it marginally bigger. In practice this API sends JSON —
# a full briefing is tens of kilobytes, and compresses about 6:1.
COMPRESSIBLE_TYPES = frozenset({
    'application/json',
    'text/plain',
})

# --------------------------------------------------------------------------
# Content Security Policy
# --------------------------------------------------------------------------

# This service returns JSON, never a page, so its policy permits nothing at
# all. That is the standard posture for an API: if a response were ever
# rendered as a document — a browser sniffing it, a proxy mislabelling it —
# there is no script, style, frame or connection it would be allowed to load.
#
# The dashboard's own policy, which does need to allow its scripts, the map
# tiles and this API, lives with the dashboard in
# frontend/public/staticwebapp.config.json.
CSP = "default-src 'none'; frame-ancestors 'none'"

SECURITY_HEADERS = {
    # Stop the browser from guessing a Content-Type and executing a JSON
    # response as script.
    'X-Content-Type-Options': 'nosniff',
    # Clickjacking: this app is never meant to be framed.
    'X-Frame-Options': 'DENY',
    # Don't leak the route being analysed to CDNs and tile servers via Referer.
    'Referrer-Policy': 'no-referrer',
    # No reason for this app to reach for hardware or location.
    'Permissions-Policy': 'geolocation=(), camera=(), microphone=(), usb=(), payment=()',
    'Content-Security-Policy': CSP,
    'Cross-Origin-Opener-Policy': 'same-origin',
    # Werkzeug advertises its exact version by default, which is free
    # reconnaissance for anyone matching against a CVE list. This covers the
    # development server; gunicorn discards an application's Server header and
    # writes its own, so production sets the name in gunicorn.conf.py.
    'Server': 'NavPort',
}


def client_ip() -> str:
    """The caller's address, trusting proxy headers only when configured to.

    Behind Azure's ingress the socket peer is the load balancer, so without
    X-Forwarded-For every client shares one bucket and the rate limiter is
    useless. Exposed directly, the opposite is true: the header is attacker
    controlled and trusting it makes the limiter trivially bypassable. Which
    situation we're in is deployment knowledge, so it comes from config.
    """
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            # Left-most entry is the original client; the rest are hops.
            return forwarded.split(',')[0].strip()

    return request.remote_addr or 'unknown'


class SlidingWindowLimiter:
    """Per-key sliding-window request counter.

    In-process and therefore per-worker: with four gunicorn workers the
    effective limit is four times the configured one. For a student project
    fronting a free public API that is the right trade — the alternative is
    running Redis alongside it. The limit is set low enough that 4x is still a
    sane ceiling.
    """

    def __init__(self, max_entries: int = 4096):
        self._hits: OrderedDict[str, deque] = OrderedDict()
        self._lock = Lock()
        self._max_entries = max_entries

    def check(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, seconds_until_retry)."""
        now = time.monotonic()
        cutoff = now - window

        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = deque()
                self._hits[key] = hits

            # Keep the map from growing without bound off a spoofed-IP flood.
            self._hits.move_to_end(key)
            while len(self._hits) > self._max_entries:
                self._hits.popitem(last=False)

            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= limit:
                return False, max(1, int(window - (now - hits[0])))

            hits.append(now)
            return True, 0


limiter = SlidingWindowLimiter()

# Only the briefing gets the tighter budget. It is the one endpoint that fans a
# single request out into seven upstream calls, so it is the one that can get
# the deployment throttled by aviationweather.gov.
#
# `/api/alternates` and `/api/pirep-reports` deliberately are *not* here: they
# cost one upstream call each, and they are driven by the user clicking around
# the dashboard. Opening pilot reports for a dozen stations along a route is
# ordinary use, and a 10-per-minute cap would break it.
EXPENSIVE_ENDPOINTS = {
    '/api/enhanced-flight-plan',
}


def _is_expensive(path: str) -> bool:
    return any(path == route or path.startswith(route + '/') for route in EXPENSIVE_ENDPOINTS)


def install_security(app) -> None:
    """Attach rate limiting, security headers, gzip and error handlers."""

    # ---------------------------------------------------------------- limits
    @app.before_request
    def _rate_limit():
        if not request.path.startswith('/api/') or request.path == '/api/health':
            return None

        key = client_ip()
        limit = BRIEFING_RATE_LIMIT if _is_expensive(request.path) else RATE_LIMIT_REQUESTS
        scope = 'briefing' if _is_expensive(request.path) else 'api'

        allowed, retry_after = limiter.check(f'{scope}:{key}', limit, RATE_LIMIT_WINDOW_SECONDS)
        if allowed:
            return None

        log.warning("Rate limit hit: %s on %s", key, request.path)
        response = jsonify({
            'error': 'Too many requests — slow down and try again shortly.',
            'retry_after_seconds': retry_after,
        })
        response.status_code = 429
        response.headers['Retry-After'] = str(retry_after)
        return response

    # --------------------------------------------------------------- headers
    @app.after_request
    def _headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        # HSTS only makes sense once TLS is actually terminating in front of
        # us; sending it over plain HTTP in development would pin localhost to
        # https in the browser and be a nuisance to undo.
        if IS_PRODUCTION:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Weather goes stale within minutes, so no intermediary may keep a copy.
        if request.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')

        return response

    # ------------------------------------------------------------------ gzip
    @app.after_request
    def _compress(response):
        accepts = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accepts.lower():
            return response

        # 2xx only — no point spending CPU on a redirect or an error page.
        if (response.status_code < 200 or response.status_code >= 300
                or 'Content-Encoding' in response.headers):
            return response

        content_type = (response.content_type or '').split(';')[0]
        if content_type not in COMPRESSIBLE_TYPES:
            return response

        # A streamed response (direct_passthrough) raises on `get_data()`.
        # This API doesn't stream today, but turning passthrough off here —
        # bounded by the size ceiling — keeps a future streamed response from
        # turning into a 500 instead of simply going out uncompressed.
        if response.direct_passthrough:
            length = response.content_length
            if length is None or length > GZIP_MAX_BYTES:
                return response
            response.direct_passthrough = False

        body = response.get_data()
        if len(body) < GZIP_MIN_BYTES or len(body) > GZIP_MAX_BYTES:
            return response

        buffer = io.BytesIO()
        # mtime=0 keeps the output byte-identical between runs, so ETags stay
        # stable across restarts instead of changing every deploy.
        with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=6, mtime=0) as handle:
            handle.write(body)

        response.set_data(buffer.getvalue())
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(response.content_length)
        response.headers.add('Vary', 'Accept-Encoding')
        return response

    # ---------------------------------------------------------------- errors
    @app.errorhandler(BadRequest)
    def _bad_request(exc: BadRequest):
        return jsonify({'error': exc.message}), exc.status

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({'error': 'Method not allowed'}), 405

    @app.errorhandler(413)
    def _too_large(_):
        return jsonify({'error': 'Request body too large'}), 413

    @app.errorhandler(Exception)
    def _unhandled(exc):
        # An exception message can carry a filesystem path, an internal
        # hostname or a fragment of the upstream URL. Log it in full for us;
        # return an opaque message to the caller.
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({'error': 'Internal server error'}), 500
