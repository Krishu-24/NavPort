# NavPort — Architecture

This document describes how NavPort is put together: its two services and how
they talk, the request flow, the module map, and why things are split the way
they are. For running it see the [README](../README.md); for Docker and Azure
see [DEPLOYMENT.md](DEPLOYMENT.md).

## 1. Two services

NavPort is a **dashboard** and an **API**, deployed separately:

| | Dashboard — `frontend/` | API — `backend/` |
|---|---|---|
| What it is | Static HTML, CSS and ES modules | Flask app returning JSON |
| Production host | Azure Static Web Apps | Azure Container Apps, from a Docker image on Docker Hub |
| Local (Python) | `frontend/tools/site.py serve`, port 8080 | `backend/wsgi.py`, port 8000 |
| Local (Docker) | nginx container, port 8080 | gunicorn container, port 8000 |
| Deployed by | `.github/workflows/frontend.yml` | `.github/workflows/backend.yml` |
| Tested by | `frontend/tests/site_test.py` | `backend/tests/api_test.py` |

They used to be one process: Flask served the dashboard's files as well as the
API. Splitting them means each runs on the service that suits it — a global
static host for files, a container platform that scales to zero for code — and
each can be redeployed without touching the other. Changing a stylesheet no
longer rebuilds a Docker image.

The cost of the split is that the dashboard and the API are now on **different
origins**, which the browser treats as strangers. Three things follow from
that, and each has one home:

1. **The page has to be told where the API is.** A relative
   `fetch('/api/...')` would go to the static site, which has no API.
   `frontend/public/js/api-config.js` sets the address before the app starts.
   The committed copy is the local default (port 8000 of whichever machine
   served the page); the deploy workflow overwrites it with the production
   API's address via `site.py configure`. The address isn't a secret — every
   visitor's browser sees it — but it is per-environment, so it lives in
   deployment configuration, not in the code.

2. **The API has to allow the dashboard's origin (CORS).** The browser sends
   the request either way, but only hands the response to the page if the API
   names the page's origin in `Access-Control-Allow-Origin`. That allowlist is
   `NAVPORT_CORS_ORIGINS` on the API. A JSON `POST` (a briefing) is preceded by
   a preflight `OPTIONS` request that must also be approved. In production the
   allowlist is explicit — never `*`, which would let any website drive this API
   with its visitors' IP addresses and burn the shared upstream quota.

3. **Each side has its own security headers.** The dashboard's
   Content-Security-Policy must allow its scripts, the map tiles and the API;
   it lives in `frontend/public/staticwebapp.config.json`, which Azure reads
   directly, and `site.py` turns the same file into the dev server's headers
   and the nginx container's config so the three can't drift. The API returns
   only JSON, so its policy allows nothing at all (`default-src 'none'`).

## 2. High-level flow

```
 Browser
   │
   │ 1. GET /  (index.html, css, js)           ┌──────────────────────────────┐
   ├──────────────────────────────────────────▶│ Dashboard                     │
   │◀──────────────────────────────────────────│ Static Web Apps / site.py /   │
   │                                           │ nginx                         │
   │                                           └──────────────────────────────┘
   │
   │ 2. OPTIONS /api/v1/briefings  (CORS preflight)
   │ 3. POST    /api/v1/briefings  (JSON flight plan)
   ├──────────────────────────────────────────▶┌──────────────────────────────┐
   │◀──────────────────────────────────────────│ API — Flask                   │
   │   JSON: route, timeline, risk,            │ routes/flight_routes.py       │
   │   NOTAMs, briefing                        └──────────────┬───────────────┘
   │                                                          │
   │ 4. GET /api/v1/airports/{icao}/pireps,                   ▼
   │    GET /api/v1/airports/{icao}/alternates┌──────────────────────────────┐
   │    (on demand)                           │ WeatherProcessor               │
   │                                          │ services/weather_service.py    │
   │                                          └──────────────┬───────────────┘
   │                                                         │ 7 concurrent requests
   │                                                         ▼
   │                                    ┌────────────────────────────────────┐
   │                                    │ aviationweather.gov/api/data       │
   │                                    │ METAR · TAF · PIREP · SIGMET ·     │
   │                                    │ G-AIRMET · CWA · station info      │
   │                                    └────────────────────────────────────┘
```

1. The browser loads the dashboard (`frontend/public/index.html`) from the
   static host. `api-config.js` runs first and tells the app where the API is.
2. Submitting the flight plan sends `POST /api/v1/briefings` to the
   API. Because it's a cross-origin JSON POST, the browser first sends an
   `OPTIONS` preflight, which the API approves for the dashboard's origin.
3. `WeatherProcessor.calculate_flight_path()` resolves each ICAO code to
   coordinates — from the bundled airport database, falling back to the
   upstream `/stationinfo` — then builds great-circle segments with a
   haversine distance calculation and per-15-minute time intervals.
4. `WeatherProcessor.get_comprehensive_weather()` fires 7 concurrent requests
   (`ThreadPoolExecutor`) against the Aviation Weather Center API for METARs,
   TAFs, PIREPs, SIGMETs, G-AIRMETs and CWAs, bounded by the route's bounding
   box. Responses are cached for five minutes (`cache.py`). NOTAMs are
   generated locally (see §6).
5. `WeatherProcessor.create_timeline_analysis()` walks every interval,
   attaches the nearest real/simulated weather, hazards and raw
   METAR/TAF/PIREP snippets, and categorizes severity (Clear / Significant /
   Severe).
6. `SimpleNLPProcessor` turns the raw timeline into a plain-English briefing
   and a risk score/recommendation. The score is an *exposure* figure — how
   much of the route is affected, weighted by how badly — but the LOW /
   MODERATE / HIGH verdict is set by the worst conditions on the route, not by
   the average of it. Averaging alone let nine clear intervals either side of
   one severe one report "LOW RISK — conditions acceptable for flight
   operations" directly beneath a "Severe" outlook. `backend/tests/test_risk.py`
   pins the cases.
7. The JSON response drives every dashboard card; PIREPs and alternates for a
   specific airport are fetched on demand when the user opens them.

## 3. The API as a REST service

### Constraints

NavPort's API follows the REST architectural constraints:

- **Client–server.** The dashboard and the API are separate programs on
  separate hosts that share nothing but HTTP. The desktop shells are a second
  client of the same API.
- **Stateless.** The API keeps no session; every request carries everything
  needed to answer it. That is what lets Azure scale it to zero when idle and
  run two copies under load — any copy can answer any request. (The rate
  limiter and the weather cache are per-process optimisations, not session
  state: losing either changes speed, never an answer.)
- **Cacheable.** Every response says whether it may be reused. Weather —
  briefings, alternates, PIREPs, health — is `Cache-Control: no-store`, because
  it goes stale and no intermediary should serve an old briefing. An airport
  (`GET /api/v1/airports/{icao}`) is `public, max-age=86400`: it doesn't move.
  The API's own description is cacheable for five minutes. Upstream weather is
  separately cached server-side for five minutes.
- **Layered.** Clients can't tell whether they reach the API directly or
  through Azure's ingress proxy — which is why `NAVPORT_TRUST_PROXY` exists, to
  recover the real client address from `X-Forwarded-For` behind that layer.
- **Uniform interface.** Covered in the rest of this section: resources with
  their own URLs, methods with standard meanings, self-describing messages,
  and links between resources.

### Resources

| Resource | URL | Methods | Archetype |
|---|---|---|---|
| The API | `/api/v1` | `GET` | document — the entry point |
| Airports | `/api/v1/airports?codes=…` | `GET` | collection, filtered by query |
| An airport | `/api/v1/airports/{icao}` | `GET` | document |
| Its alternates | `/api/v1/airports/{icao}/alternates` | `GET` | sub-collection |
| Its pilot reports | `/api/v1/airports/{icao}/pireps` | `GET` | sub-collection |
| Briefings | `/api/v1/briefings` | `POST` | collection — submit a plan, get its briefing |
| Parse | `/api/v1/flight-plans/parse` | `POST` | controller — an action, not a thing |
| Health | `/api/v1/health` | `GET` | document |
| The contract | `/api/v1/openapi.json` | `GET` | document |

URLs are nouns, plural for collections, and nested where one resource belongs
to another — an airport's alternates live under that airport. `GET` only ever
reads, so it is safe to repeat or prefetch; `POST` carries a body to be
processed. The parse endpoint is the deliberate exception: it is an operation
rather than a resource, so — following the usual convention for *controller*
resources — it is named with a verb under the collection it acts on.

A briefing is computed, not stored, so `POST /api/v1/briefings` answers `200`
with the briefing rather than `201 Created` with a `Location` to fetch it
from: there is nothing to fetch later. Storing briefings would make that a
true create, at the cost of state the API currently doesn't keep.

### Messages

Representations are JSON. Status codes carry the outcome — `400` invalid
input, `404` no such resource, `405` wrong method, `413` body too large, `429`
rate limited, `503` upstream unavailable — and the headers carry what the
status implies: a `405` lists the methods that *are* allowed (`Allow`), a
`429` says when to come back (`Retry-After`).

Every error body is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
**Problem Details** document, media type `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "No airport with identifier ZZZZ in the database",
  "instance": "/api/v1/airports/ZZZZ"
}
```

One shape for every failure means a client has one error path, and the
`detail` is written to be shown to a person. Errors never include internals;
`backend/tests/api_test.py` checks for stack traces and file paths.

### Links

`GET /api/v1` lists every resource as a link, using
[RFC 6570](https://www.rfc-editor.org/rfc/rfc6570) URI templates where a value
has to be filled in (`/api/v1/airports/{icao}`). An airport links to its own
alternates and pilot reports. A client can start at one known address and
follow links rather than building URLs — the idea behind level 3 of the
Richardson maturity model, applied here where it is cheap. Levels 1 and 2 —
resources, and HTTP methods and status codes used for their meaning — hold
throughout.

### The contract

`backend/navport/openapi.py` describes the whole API in **OpenAPI 3.1**, served
at `GET /api/v1/openapi.json`. The limits it documents (waypoints per route,
codes per lookup, text length) are read from `config.py`, the same values the
validators enforce, so the documentation can't drift from the behaviour. The
dashboard's `/docs/` page renders it with Swagger UI, from which every
endpoint can be called against the live API. The API test checks that every
link in the index is documented.

### Versioning

The version is in the path, `/api/v1`, where it is visible in every URL and
every access-log line. The API's first addresses were unversioned and partly
named after actions (`/api/enhanced-flight-plan`, `/api/pirep-reports/KJFK`).
They still work — `routes/legacy_routes.py` maps each to the same handler as
its v1 successor — so no existing client broke when v1 shipped. Each of their
responses carries three standard headers:

```
Deprecation: @1791763200                                RFC 9745 — deprecated since 12 Oct 2026
Sunset: Tue, 12 Jan 2027 00:00:00 GMT                   RFC 8594 — may stop working after
Link: </api/v1/briefings>; rel="successor-version"      RFC 5829 — use this instead
```

Their error bodies also keep the old `error` member beside the Problem Details
fields, because that is what their clients read. Rate limits are counted per
handler, not per URL, so the old and new address of one endpoint share a
budget.

### NavPort as a REST client

NavPort is also a **REST client**: one briefing request becomes about seven
requests to the Aviation Weather Center's own REST API, whose answers are
merged, analysed and cached. In that sense the API is an aggregator, turning
seven raw data feeds into one answer shaped for the dashboard.

## 4. Module map

```
NavPort/
├── backend/                      # The API
│   ├── wsgi.py                   # WSGI entry: gunicorn imports `app`; run directly for the dev server
│   ├── gunicorn.conf.py          # Production server: gthread workers, timeouts, Server header
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── navport/
│   │   ├── __init__.py           # App factory: CORS, security, routes
│   │   ├── config.py             # Settings with production-safe defaults, lookup tables
│   │   ├── security.py           # Security headers, rate limiting, gzip, error handlers
│   │   ├── problems.py           # RFC 9457 Problem Details — the shape of every error
│   │   ├── openapi.py            # The OpenAPI 3.1 contract, built from config limits
│   │   ├── validation.py         # Input validation — bad input is 4xx, not 500
│   │   ├── cache.py              # TTL cache for upstream calls
│   │   ├── telemetry.py          # Live console reporting (development)
│   │   ├── data/airports.json.gz # OurAirports extract (public domain), 34k identifiers
│   │   ├── models/
│   │   │   └── pirep.py          # PIREP dataclass + raw-text parsing/formatting
│   │   ├── services/
│   │   │   ├── airports.py       # Airport identity lookups over the bundled database
│   │   │   ├── flight_rules.py   # FAA categories, wind components, bearings (pure)
│   │   │   ├── pirep_service.py  # Fetches & parses PIREPs for a single station
│   │   │   ├── nlp_processor.py  # METAR decoding, briefing text, risk scoring
│   │   │   └── weather_service.py# Flight path, concurrent fetch, timeline, alternates
│   │   └── routes/
│   │       ├── __init__.py       # The v1 and legacy blueprints, and registration
│   │       ├── meta.py           # /api/v1 index, /health, /openapi.json
│   │       ├── flight_routes.py  # /airports, /airports/{icao}, …/alternates, /briefings, /flight-plans/parse
│   │       ├── pirep_routes.py   # /airports/{icao}/pireps
│   │       └── legacy_routes.py  # The original /api/... addresses, as deprecated aliases
│   └── tests/
│       ├── api_test.py           # End-to-end against a running API
│       └── test_risk.py          # Risk scoring, no server
│
├── frontend/                     # The dashboard
│   ├── public/                   # Served as-is — this folder is what gets deployed
│   │   ├── index.html            # Dashboard shell (rail + card grid)
│   │   ├── staticwebapp.config.json  # Headers, MIME types, cache rules (Azure reads it)
│   │   ├── manifest.webmanifest, sw.js, offline.html   # PWA
│   │   ├── css/                  # tokens · layout · components · dashboard · platform · print · board
│   │   ├── js/
│   │   │   ├── main.js           # Entry point (ES module): boot + orchestration
│   │   │   ├── api-config.js     # Where the API is (rewritten per deployment)
│   │   │   ├── config.js         # Resolves the API base URL; apiUrl()
│   │   │   ├── native.js         # Native-shell detection, before first paint
│   │   │   ├── core/             # api (fetch layer) · state · dom · format · idents
│   │   │   ├── ui/               # shell · theme · recent · toast · offline · board (split-flap)
│   │   │   └── views/            # overview · risk · ribbon · map · charts · notams · timeline · alternates · pireps
│   │   ├── docs/                 # API reference: Swagger UI over the API's openapi.json
│   │   ├── vendor/               # Leaflet, Chart.js, Swagger UI, IBM Plex
│   │   └── assets/               # icon.png + generated icons
│   ├── tools/site.py             # Dev server · nginx config · `configure --api-base`
│   ├── tests/site_test.py        # End-to-end against any served copy
│   ├── Dockerfile, nginx.conf    # Local container only
│
├── scripts/dev.py                # Runs both services for local development
├── docker-compose.yml            # Both services as containers
└── desktop/                      # Tauri shells: bundle frontend/public, call the hosted API
```

### Dashboard conventions

The dashboard has **no build step and no bundler** — the browser loads
`js/main.js` as a native ES module (`<script type="module">`) and resolves the
`import` graph itself. The files in `frontend/public/` are exactly the files
that get served, which keeps deployment a plain upload while still giving real
module boundaries:

- **`core/`** is dependency-free logic (fetching, formatting, state). It never
  touches the DOM beyond the helpers in `dom.js`. Every API call goes through
  `apiUrl()` in `config.js`, so nothing assumes the API shares the page's
  origin.
- **`views/`** modules each own one card and expose a single `render*(data)`
  function. They read from the payload and write to their own container — no
  view reaches into another view's markup.
- **Events are delegated and declarative.** There is no inline `onclick`
  anywhere; `initTimeline()`, `initRibbonLink()` and `initPirepModal()` bind
  one listener each at boot and dispatch on `data-*` attributes, so re-rendering
  a section never re-binds or leaks handlers.
- **Untrusted text is escaped** (`esc()`) before it reaches any `innerHTML`;
  most rendering uses `el()`, which sets text nodes and cannot inject markup.
- **No inline scripts.** Even the API address is an external file, so the CSP
  can refuse inline JavaScript — the rule that actually stops injected script
  from running.
- **Third-party runtime deps are vendored**, not loaded from a CDN. `Chart.js`,
  `Leaflet` and the IBM Plex fonts live in `frontend/public/vendor/`, fetched
  and hash-verified by `scripts/vendor_assets.py`. They used to come from
  jsdelivr, unpkg and Google Fonts; the failure mode was bad, because Leaflet
  not loading leaves a blank grey panel where the map should be with nothing
  in the UI to say so. It also means `script-src` and `font-src` are plain
  `'self'`, and the packaged desktop and mobile apps open without a network.
- Basemap tiles are still a live request to Esri. If the tiles are
  unreachable the map degrades to a labelled placeholder and the rest of the
  dashboard is unaffected.

## 5. Why the API is split this way

- **`models/` vs `services/`** — `pirep.py` is pure data + parsing (no I/O),
  so it's trivially unit-testable and reusable by both `pirep_service.py`
  (station lookups) and `weather_service.py` (route-wide PIREP fetches).
- **`weather_service.py` stays one class** — `WeatherProcessor` owns a single
  `requests.Session` and a lot of interdependent state (bbox, timeline,
  hazard rules); splitting it further would just move private helper calls
  across file boundaries without adding clarity.
- **Routes are thin** — each Flask view function only validates input, calls
  into a service, and shapes the JSON response. No business logic lives in
  `routes/`.
- **The app factory serves nothing but the API.** It disables Flask's static
  folder entirely, so a request for a dashboard file gets a `404` from the API
  rather than a quiet answer — `api_test.py` checks this, so the two services
  can't drift back into one.

## 6. NOTAMs are simulated

Real-time NOTAM feeds (FAA NOTAM Search, SWIM, or commercial APIs) require
paid/authenticated access. `WeatherProcessor.get_notams()` deterministically
generates realistic, time-appropriate NOTAMs (seeded by airport + date) so
the rest of the pipeline — severity classification, timeline hazards, the
NOTAM cards — can be exercised end-to-end without a paid subscription. Every
generated NOTAM is labeled `"source": "Demo Data (Time-Based)"` in the API
response so this is never mistaken for a live feed. See the README for
pointers on wiring in a real NOTAM source.

## 7. Historical / forecast weather simulation

The Aviation Weather Center API only reliably serves METARs/PIREPs for the
last few hours and TAFs a few hours ahead. For timeline intervals outside
that window (e.g. a route 10 hours from departure, or a "departure" 3 days
in the past), `simulate_historical_weather()` derives a deterministic,
seeded approximation from the nearest real observation so the flight's full
timeline can still be rendered and risk-scored.

## 8. Data flow guarantees

- All timestamps are UTC end-to-end (API, backend processing, and the
  dashboard clock/timeline labels).
- Departure time is bounded server-side to `[-15 days, +4 hours]` from now
  (`backend/navport/config.py`), matching the Aviation Weather Center's own
  data window; violations return `400` with a descriptive error.
- Every external API call has a timeout (10–15s) and is wrapped so a single
  failing product (e.g. G-AIRMET down) degrades to an empty list instead of
  failing the whole request.

## 9. How it runs in production

- **The API** is **gunicorn inside a Docker image** ([backend/Dockerfile](../backend/Dockerfile),
  [gunicorn.conf.py](../backend/gunicorn.conf.py)), published to Docker Hub and
  run by Azure Container Apps, which terminates TLS and forwards to port
  **8000**. `NAVPORT_ENV=production` and `NAVPORT_TRUST_PROXY=true` are set
  there, and `NAVPORT_CORS_ORIGINS` names the dashboard's address.
  `/api/v1/health` is the liveness probe: it only checks that the app started and
  `airports.json.gz` loaded — not that aviationweather.gov is reachable — so an
  upstream outage cannot make the orchestrator reboot the container in a loop.
  Scale-to-zero (`minReplicas: 0`) is what keeps it free; the first request
  after idle pays a few seconds of cold start.
- **The dashboard** is the contents of `frontend/public/`, uploaded to Azure
  Static Web Apps after `site.py configure` has written the API's address into
  it. Static Web Apps serves it from a global edge network and applies the
  headers in `staticwebapp.config.json`.

Commands, settings and the cost reasoning are in [DEPLOYMENT.md](DEPLOYMENT.md).
