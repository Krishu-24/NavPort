# syntax=docker/dockerfile:1

# NavPort production image.
#
# Two stages. The builder compiles the dependencies into a venv; the runtime
# copies only the finished packages in. That keeps pip, its build tooling and
# any transient compiler out of the shipped image — a smaller image and a
# smaller attack surface, since what isn't installed can't be exploited.
#
# Azure Container Apps runs this file. Local rehearsal: `docker compose up --build`.
# Why this service, free-tier math, and the Azure create commands:
#   docs/DEPLOYMENT.md

# --------------------------------------------------------------------------
# Stage 1 — build dependencies
# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .

# A virtualenv rather than --user, so the whole tree can be copied as one unit
# and lands at a predictable path in the runtime stage.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install -r requirements.txt

# --------------------------------------------------------------------------
# Stage 2 — runtime
# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="NavPort" \
      org.opencontainers.image.description="Aviation weather intelligence and route risk briefing" \
      org.opencontainers.image.source="https://github.com/Krishu-24/NavPort" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    NAVPORT_ENV=production \
    PORT=8000

# curl is here for the HEALTHCHECK below and nothing else. Installing it
# explicitly and cleaning the apt lists in the same layer keeps the package
# index out of the image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

# Run as a normal user. A container process running as root that gets code
# execution is one kernel bug away from the host; an unprivileged one is not.
# A fixed uid/gid keeps file ownership predictable if a volume is mounted.
RUN groupadd --gid 10001 navport \
    && useradd --uid 10001 --gid navport --create-home --shell /usr/sbin/nologin navport

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Ownership is set at copy time rather than with a later `chown -R`, which
# would duplicate the whole tree into a second layer.
COPY --chown=navport:navport backend/ ./backend/
COPY --chown=navport:navport frontend/ ./frontend/
COPY --chown=navport:navport gunicorn.conf.py run.py ./

USER navport

EXPOSE 8000

# Hits the app's own health endpoint, which reports whether the bundled
# airport database actually loaded. It deliberately does not call
# aviationweather.gov, so an upstream outage cannot make the orchestrator
# decide this container is broken and restart it in a loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent --show-error "http://127.0.0.1:${PORT}/api/health" > /dev/null || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "run:app"]
