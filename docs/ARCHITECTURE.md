# NavPort — Architecture

This document describes how NavPort is put together: the request flow, the
module map, and why the backend is split the way it is. For install/run
instructions see the [README](../README.md).

## 1. High-level flow

```
┌──────────────┐        GET /                 ┌──────────────────────┐
│              │ ───────────────────────────▶  │  Flask static server │
│   Browser    │        (index.html, css, js)  │  (backend/__init__)  │
│  (frontend/) │ ◀───────────────────────────  └──────────────────────┘
│              │
│              │        POST /api/enhanced-flight-plan
│              │ ───────────────────────────▶  ┌──────────────────────┐
│              │                                │  flight_routes.py    │
│              │ ◀───────────────────────────   │  (Blueprint)         │
│              │        JSON: route, timeline,  └──────────┬───────────┘
│              │        risk, NOTAMs, charts               │
│              │                                            ▼
│              │        GET /api/pirep-reports/<id>  ┌──────────────────────┐
│              │ ───────────────────────────▶        │  WeatherProcessor     │
│              │ ◀───────────────────────────         │  (services/weather_   │
└──────────────┘        JSON: PIREPs                  │  service.py)          │
                                                        └──────────┬───────────┘
                                                                   │ concurrent
                                                                   │ fetch (7 workers)
                                                                   ▼
                                          ┌────────────────────────────────────┐
                                          │  aviationweather.gov/api/data       │
                                          │  METAR · TAF · PIREP · SIGMET ·     │
                                          │  G-AIRMET · CWA · station info      │
                                          └────────────────────────────────────┘
```

1. The browser loads the single-page dashboard (`frontend/index.html`) from
   Flask's static file handler.
2. The sidebar form posts a flight plan to `POST /api/enhanced-flight-plan`.
3. `WeatherProcessor.calculate_flight_path()` resolves each ICAO code to
   coordinates (`/stationinfo`), then builds great-circle segments with a
   haversine distance calculation and per-15-minute time intervals.
4. `WeatherProcessor.get_comprehensive_weather()` fires 7 concurrent requests
   (`ThreadPoolExecutor`) against the Aviation Weather Center API for METARs,
   TAFs, PIREPs, SIGMETs, G-AIRMETs and CWAs, bounded by the route's bounding
   box. NOTAMs are generated locally (see §4).
5. `WeatherProcessor.create_timeline_analysis()` walks every interval,
   attaches the nearest real/simulated weather, hazards and raw
   METAR/TAF/PIREP snippets, and categorizes severity (Clear / Significant /
   Severe).
6. `SimpleNLPProcessor` turns the raw timeline into a plain-English briefing
   and a risk score/recommendation.
7. The JSON response drives every dashboard card; PIREPs for a specific
   station are fetched on demand when a user opens the "Pilot Reports" modal.

## 2. Module map

```
NavPort/
├── run.py                     # Entry point: creates and runs the Flask app
├── run.bat                    # Windows launcher (venv + deps + run)
├── requirements.txt
│
├── backend/
│   ├── __init__.py            # App factory: static file serving, CORS, blueprints
│   ├── config.py              # Constants: API base URL, host/port, lookup tables
│   ├── data/airports.json.gz  # OurAirports extract (public domain), 34k identifiers
│   │
│   ├── models/
│   │   └── pirep.py           # PIREP dataclass + raw-text parsing/formatting
│   │
│   ├── services/
│   │   ├── flight_rules.py    # FAA categories, wind components, bearings (pure)
│   │   ├── pirep_service.py   # Fetches & parses PIREPs for a single station
│   │   ├── nlp_processor.py   # METAR decoding, briefing text, risk scoring
│   │   └── weather_service.py # Flight path calc, concurrent fetch, timeline, alternates
│   │
│   ├── routes/
│   │   ├── flight_routes.py   # /api/enhanced-flight-plan, /api/alternates, /api/process-natural-language
│   │   └── pirep_routes.py    # /api/pirep-reports/<station_id>
│   └── telemetry.py           # Live console reporting
│
├── frontend/
│   ├── index.html             # Dashboard shell (rail + card grid)
│   ├── css/
│   │   ├── print.css          # Print / save-as-PDF layout
│   │   ├── tokens.css         # Design tokens, reset, base type, keyframes
│   │   ├── layout.css         # Shell: rail, topbar, content grid, responsive
│   │   ├── components.css     # Buttons, fields, cards, pills, modal, toasts
│   │   └── dashboard.css      # Views: KPIs, gauge, map, ribbon, timeline
│   ├── js/
│   │   ├── main.js            # Entry point (ES module): boot + orchestration
│   │   ├── core/
│   │   │   ├── api.js         # fetch layer for /api/*
│   │   │   ├── state.js       # Tiny observable store
│   │   │   ├── dom.js         # el()/$/esc/animateNumber helpers
│   │   │   └── format.js      # Severity vocabulary, time & unit formatting
│   │   ├── ui/
│   │   │   ├── shell.js       # UTC clock, off-canvas rail, view switching
│   │   │   ├── theme.js       # Light/dark switching + repaint broadcast
│   │   │   ├── recent.js      # Recently analysed routes
│   │   │   └── toast.js       # Corner notifications
│   │   └── views/
│   │       ├── overview.js    # Route chip + KPI tiles
│   │       ├── risk.js        # Arc gauge, breakdown, briefing, source counts
│   │       ├── ribbon.js      # Severity strip (linked to the timeline)
│   │       ├── map.js         # Leaflet route map
│   │       ├── charts.js      # Chart.js wind + visibility
│   │       ├── notams.js      # NOTAM cards
│   │       ├── timeline.js    # Interval rows + raw METAR/TAF panels
│   │       ├── alternates.js  # Diversion options
│   │       └── pireps.js      # Pilot-report modal
│   └── assets/icon.png
│
└── docs/
    └── ARCHITECTURE.md        # This file
```

### Frontend conventions

The frontend has **no build step and no bundler** — the browser loads
`js/main.js` as a native ES module (`<script type="module">`) and resolves the
`import` graph itself. That keeps `python run.py` as the only thing needed to
run the app while still giving real module boundaries:

- **`core/`** is dependency-free logic (fetching, formatting, state). It never
  touches the DOM beyond the helpers in `dom.js`.
- **`views/`** modules each own one card and expose a single `render*(data)`
  function. They read from the payload and write to their own container — no
  view reaches into another view's markup.
- **Events are delegated and declarative.** There is no inline `onclick`
  anywhere; `initTimeline()`, `initRibbonLink()` and `initPirepModal()` bind
  one listener each at boot and dispatch on `data-*` attributes, so re-rendering
  a section never re-binds or leaks handlers.
- **Untrusted text is escaped** (`esc()`) before it reaches any `innerHTML`;
  most rendering uses `el()`, which sets text nodes and cannot inject markup.
- Third-party runtime deps are loaded from CDN (`Chart.js`, `Leaflet`). If
  Leaflet or its tiles are unreachable, the map degrades to a labelled
  placeholder and the rest of the dashboard is unaffected.

## 3. Why it's split this way

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
- **The app factory (`backend/__init__.py`)** wires `frontend/` up as Flask's
  static folder with `static_url_path=""`, so `index.html`, `css/`, `js/` and
  `assets/` are served with no custom static route needed — only `/` gets an
  explicit view to hand back `index.html`.

## 4. NOTAMs are simulated

Real-time NOTAM feeds (FAA NOTAM Search, SWIM, or commercial APIs) require
paid/authenticated access. `WeatherProcessor.get_notams()` deterministically
generates realistic, time-appropriate NOTAMs (seeded by airport + date) so
the rest of the pipeline — severity classification, timeline hazards, the
NOTAM cards — can be exercised end-to-end without a paid subscription. Every
generated NOTAM is labeled `"source": "Demo Data (Time-Based)"` in the API
response so this is never mistaken for a live feed. See the README for
pointers on wiring in a real NOTAM source.

## 5. Historical / forecast weather simulation

The Aviation Weather Center API only reliably serves METARs/PIREPs for the
last few hours and TAFs a few hours ahead. For timeline intervals outside
that window (e.g. a route 10 hours from departure, or a "departure" 3 days
in the past), `simulate_historical_weather()` derives a deterministic,
seeded approximation from the nearest real observation so the flight's full
timeline can still be rendered and risk-scored.

## 6. Data flow guarantees

- All timestamps are UTC end-to-end (API, backend processing, and the
  frontend clock/timeline labels).
- Departure time is bounded server-side to `[-15 days, +4 hours]` from now
  (`backend/config.py`), matching the Aviation Weather Center's own data
  window; violations return `400` with a descriptive error.
- Every external API call has a timeout (10–15s) and is wrapped so a single
  failing product (e.g. G-AIRMET down) degrades to an empty list instead of
  failing the whole request.
