# NavPort

A flight weather dashboard for pilots and aviation planners. Enter a route,
and NavPort pulls live METARs, TAFs, PIREPs, SIGMETs, G-AIRMETs and CWAs
along the flight path, builds a 15-minute interval timeline, and produces a
plain-English briefing with an automated risk assessment.

## How to Run

### Windows — one-click

Double-click **[`run.bat`](run.bat)**. It will:

1. Check that Python is installed (and tell you where to get it if not).
2. Create a virtual environment in `.venv/` — skipped if one already exists.
3. Install dependencies from `requirements.txt` — skipped if they're already
   up to date.
4. Start the server and print `http://localhost:5000`.

Re-running `run.bat` any time (including after a fresh `git pull`) is safe —
it only re-installs dependencies when `requirements.txt` has actually
changed, and never re-creates an existing virtual environment.

### Manual setup (Windows / macOS / Linux)

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
python run.py
```

Then open **http://localhost:5000**.

## Documentation Hub

| Doc | What's in it |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Request flow, module map, diagrams, why the backend is split the way it is |
| This README | Setup, features, API endpoints, project layout |

## What You Get

| Capability | Details |
|---|---|
| **Route weather timeline** | 15-minute interval breakdown of the whole route, with severity (Clear / Significant / Severe) per segment |
| **Live aviation data** | METAR, TAF, PIREP, SIGMET, G-AIRMET, CWA — fetched concurrently from aviationweather.gov |
| **NOTAMs** | Time-appropriate NOTAM cards per airport (see [Data Sources](#data-sources) — currently simulated demo data) |
| **Risk assessment** | Automated LOW / MODERATE / HIGH risk score with a recommendation, derived from the timeline |
| **Plain-English briefing** | METAR/route conditions summarized in natural language (regex-based NLP, no external LLM call) |
| **Pilot reports (PIREPs)** | Per-station PIREP lookup in a modal, toggle between a decoded summary and the raw report text |
| **Raw data on demand** | Show/hide the raw METAR and TAF text behind any timeline interval without leaving the page |
| **Route map** | Live map with the flight path drawn segment-by-segment in its severity colour, airport markers and per-interval condition popups |
| **Severity ribbon** | Scrubbable strip of the entire route — hover to highlight, click to jump to that interval |
| **Charts** | Wind (sustained + gusts) and visibility, colour-banded by aviation minimums |
| **Responsive dashboard UI** | Dark flight-deck theme, animated risk gauge, skeleton loading states, off-canvas flight plan on mobile |

## Architecture at a Glance

```
Browser (frontend/)  ──▶  Flask (backend/routes/)  ──▶  WeatherProcessor (backend/services/)
                                                              │
                                                              ▼
                                            aviationweather.gov/api/data
                                     (METAR · TAF · PIREP · SIGMET · G-AIRMET · CWA)
```

Full request flow, module responsibilities and design rationale are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository Layout

```
NavPort/
├── run.bat                    # Windows one-click launcher
├── run.py                     # Entry point (python run.py)
├── requirements.txt
├── backend/
│   ├── __init__.py            # Flask app factory
│   ├── config.py              # Constants & lookup tables
│   ├── models/pirep.py        # PIREP dataclass + raw-text parsing
│   ├── services/               # PIREP fetch, NLP, weather aggregation
│   └── routes/                 # /api/* Flask blueprints
├── frontend/
│   ├── index.html
│   ├── css/                    # tokens · layout · components · dashboard
│   ├── js/
│   │   ├── main.js             # ES module entry point
│   │   ├── core/               # api · state · dom · format
│   │   ├── ui/                 # shell · toast
│   │   └── views/              # overview · risk · ribbon · map · charts · notams · timeline · pireps
│   └── assets/icon.png
└── docs/
    └── ARCHITECTURE.md
```

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Serves the dashboard |
| `POST` | `/api/enhanced-flight-plan` | Full route analysis: weather timeline, NOTAMs, risk assessment, briefing |
| `POST` | `/api/process-natural-language` | Extracts departure/destination/waypoints/speed from free text |
| `GET` | `/api/pirep-reports/<station_id>` | PIREPs near a station (`?distance=`, `?age=`, `?raw=true\|false`) |

## Technology Stack

**Backend:** Flask, `requests`, `concurrent.futures` for parallel API calls,
regex-based NLP (no external ML/LLM dependency).

**Frontend:** Native ES modules — no bundler, no build step, no framework
runtime. Chart.js for the wind/visibility plots, Leaflet for the route map,
Inter + JetBrains Mono via Google Fonts. Dark "glass cockpit" theme driven by
CSS custom properties.

**Data:** [Aviation Weather Center](https://aviationweather.gov) public API.

## Data Sources

- **Live weather** (METAR/TAF/PIREP/SIGMET/G-AIRMET/CWA/station info): real
  data from aviationweather.gov, up to 15 days historical and a few hours of
  forecast, depending on product.
- **NOTAMs**: currently deterministic demo data (see
  [docs/ARCHITECTURE.md §4](docs/ARCHITECTURE.md#4-notams-are-simulated)) —
  real NOTAM feeds require an authenticated/paid API (FAA NOTAM Search, SWIM,
  or a commercial provider). Every generated NOTAM is labeled
  `"source": "Demo Data (Time-Based)"` in API responses so this is never
  mistaken for live data.
- **Weather outside the API's real-time window** is deterministically
  simulated from the nearest real observation so the full route timeline can
  still be rendered.

## Configuration

Environment variables (all optional, read in `backend/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `NAVPORT_HOST` | `0.0.0.0` | Bind address |
| `NAVPORT_PORT` | `5000` | Port |
| `NAVPORT_DEBUG` | `true` | Flask debug/reload mode |

## Disclaimer

This application is for informational and educational purposes only. All
weather information should be verified through official aviation weather
sources. Do not use this application as the sole source for flight planning
decisions — always consult official NOTAMs, weather briefings, and follow
applicable aviation regulations.
