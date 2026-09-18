"""Gunicorn configuration for the NavPort container.

The worker model is the decision that matters here. A NavPort briefing spends
almost all of its time waiting on aviationweather.gov — seven concurrent HTTP
calls, then a handful more — and almost none of it on CPU. Sync workers would
each sit blocked on a socket for the whole request, so a 0.5-vCPU container
would serve about two users at a time. Threads let one worker hold many
in-flight requests while they wait.
"""

import multiprocessing
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Azure Container Apps and App Service both inject the port to bind.
bind = f"0.0.0.0:{_int('PORT', 8000)}"

# --------------------------------------------------------------------------
# Workers
# --------------------------------------------------------------------------

worker_class = "gthread"

# Two workers give a second process to absorb requests while one is restarting
# or wedged, without the memory cost of one-per-core on a small container.
# Capped at the CPU count so this doesn't oversubscribe a 0.5-vCPU instance.
workers = _int("WEB_CONCURRENCY", min(2, multiprocessing.cpu_count()) or 1)
threads = _int("NAVPORT_THREADS", 8)

# Fork after importing the app, so the 34,000-entry airport database is parsed
# once and then shared with every worker through copy-on-write instead of
# being decompressed and allocated per worker.
preload_app = True

# --------------------------------------------------------------------------
# Timeouts
# --------------------------------------------------------------------------

# A cold briefing legitimately takes 7-10 seconds when every upstream call is
# a real fetch, and the default of 30s would kill it on a slow day.
timeout = _int("NAVPORT_TIMEOUT", 90)
graceful_timeout = 30

# Must exceed the idle timeout of whatever sits in front of us, or the proxy
# reuses a connection gunicorn has already closed and the client sees a 502.
keepalive = _int("NAVPORT_KEEPALIVE", 75)

# --------------------------------------------------------------------------
# Hygiene
# --------------------------------------------------------------------------

# Recycle workers periodically so a slow leak in a long-lived process can
# never accumulate into an out-of-memory kill. The jitter stops every worker
# retiring on the same request and dropping throughput to zero.
max_requests = _int("NAVPORT_MAX_REQUESTS", 1000)
max_requests_jitter = 100

# The in-process TTL cache and rate limiter live in worker memory, so a
# restart costs a cold cache. Worth it for the leak protection.

accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("NAVPORT_LOG_LEVEL", "info")

# Log the forwarded client address rather than the ingress proxy's, and record
# how long each request took.
access_log_format = '%({x-forwarded-for}i)s "%(r)s" %(s)s %(b)s %(M)sms "%(a)s"'

# Only trust X-Forwarded-* from the local ingress. Container Apps and App
# Service both proxy from inside the pod's network namespace.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")

# Bound the request line and headers so an oversized one is refused by the
# server rather than allocated by the app. Body size is capped separately in
# the Flask config (MAX_CONTENT_LENGTH).
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Writing worker temp files to /dev/shm avoids stalls on container
# filesystems, where /tmp can be backed by a slow overlay.
worker_tmp_dir = "/dev/shm"
