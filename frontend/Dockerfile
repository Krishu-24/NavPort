# syntax=docker/dockerfile:1

# NavPort dashboard image — for local runs only.
#
# In production these same files are served by Azure Static Web Apps, which
# needs no container at all. This image exists so that `docker compose up`
# runs NavPort's two halves as two containers, the same way production runs
# them as two services, and so the dashboard is served locally by a real web
# server sending the same security headers it gets in production.
#
# Built with frontend/ as the context.

# --------------------------------------------------------------------------
# Stage 1 — turn the Static Web Apps rules into nginx config
# --------------------------------------------------------------------------
# public/staticwebapp.config.json is where the dashboard's headers are defined,
# and Azure reads it directly. Generating nginx's config from that same file
# means the two can never drift apart. This stage is thrown away; only its
# output is copied forward.
FROM python:3.12-alpine AS rules

WORKDIR /build
COPY tools/site.py public/staticwebapp.config.json ./
RUN python site.py nginx-config --config staticwebapp.config.json --out /build/nginx

# --------------------------------------------------------------------------
# Stage 2 — nginx, as a non-root user
# --------------------------------------------------------------------------
# The unprivileged variant runs as uid 101 and listens on 8080 rather than 80,
# which would need root to bind. Same reasoning as the API image: a process
# that gets compromised shouldn't be root inside its container.
FROM nginxinc/nginx-unprivileged:1.30.5-alpine

LABEL org.opencontainers.image.title="NavPort dashboard (local)" \
      org.opencontainers.image.source="https://github.com/Krishu-24/NavPort" \
      org.opencontainers.image.licenses="MIT"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=rules /build/nginx/ /etc/nginx/navport/
COPY public/ /usr/share/nginx/html/

EXPOSE 8080

# busybox wget ships with alpine; no need to install curl just for this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/ || exit 1
