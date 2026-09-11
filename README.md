# NavPort

A flight weather dashboard for pilots and aviation planners. Enter a route,
and NavPort pulls live METARs, TAFs, PIREPs, SIGMETs, G-AIRMETs and CWAs
along the flight path, builds a 15-minute interval timeline, and produces a
plain-English briefing with an automated risk assessment.

## How to Run

### One-click

| Platform | Double-click |
|---|---|
| Windows | **[`run.bat`](run.bat)** |
| macOS / Linux | **[`run.command`](run.command)** |

Either one will:

1. Check that Python 3.9+ is installed (and tell you where to get it if not).
2. Create a virtual environment in `.venv/` — skipped if one already exists.
3. Install dependencies from `requirements.txt` — skipped if they're already
   up to date.
4. Start the server and print `http://localhost:5000`.

Re-running is always safe, including after a fresh `git pull` — dependencies
are only re-installed when `requirements.txt` has actually changed, and an
existing virtual environment is never re-created.

> **macOS first run:** if double-clicking opens the file in a text editor
> instead of running it, make it executable once with
> `chmod +x run.command`. From a terminal you can also just run
> `./run.command`.

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
| **Airport identity** | Every ICAO code resolves to its IATA code, airport name, city and country — 34,000 airports worldwide, bundled offline. Hover any code to roll down its meaning |
| **Density altitude** | Pressure and density altitude at both ends, flagged when it runs more than 2,000 ft above field elevation — a standard FAA briefing element |
| **Flight categories** | Standard FAA **VFR / MVFR / IFR / LIFR** for every interval, derived from ceiling and visibility — the language pilots actually plan in |
| **Diversion planning** | Nearby airports that are usable alternates for your destination, ranked by distance with ceiling, visibility, wind and bearing |
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
| **Printable briefing** | Print or save the whole briefing as a PDF, laid out as a document with a header and no page-split rows |
| **Recent routes** | The last five routes you analysed, one click to re-run |
| **Responsive dashboard UI** | Light and dark themes, animated risk gauge, skeleton loading states, off-canvas flight plan on mobile |

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
├── run.command                # macOS / Linux one-click launcher
├── run.py                     # Entry point (python run.py)
├── requirements.txt
├── WHATS-NEW.md               # What changed from the previous version
├── backend/
│   ├── __init__.py            # Flask app factory
│   ├── config.py              # Constants & lookup tables
│   ├── telemetry.py           # Live console device/traffic reporting
│   ├── models/pirep.py        # PIREP dataclass + raw-text parsing
│   ├── services/              # flight_rules · pirep · nlp · weather
│   └── routes/                # /api/* Flask blueprints
├── frontend/
│   ├── index.html
│   ├── css/                   # tokens · layout · components · dashboard · print
│   ├── js/
│   │   ├── main.js            # ES module entry point
│   │   ├── core/              # api · state · dom · format
│   │   ├── ui/                # shell · theme · recent · toast
│   │   └── views/             # overview · risk · ribbon · map · charts · notams · timeline · alternates · pireps
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
| `GET` | `/api/airports` | Resolve identifiers to IATA + name (`?codes=KJFK,EGLL`) |
| `GET` | `/api/alternates/<icao>` | Usable diversion airports near an airport (`?radius=`, `?limit=`, `?runway=`) |

## Technology Stack

**Backend:** Flask, `requests`, `concurrent.futures` for parallel API calls,
regex-based NLP and a pure-Python flight-rules engine (no external ML/LLM
dependency, no extra packages beyond `requirements.txt`).

**Frontend:** Native ES modules — no bundler, no build step, no framework
runtime. Chart.js for the wind/visibility plots, Leaflet for the route map,
IBM Plex Sans + IBM Plex Mono via Google Fonts. Light and dark themes driven
entirely by CSS custom properties.

**Data:** [Aviation Weather Center](https://aviationweather.gov) public API for
weather; [OurAirports](https://ourairports.com/data/) (public domain) for the
bundled worldwide airport database.

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
