# What's New in NavPort

NavPort is the next version of **SkyHigh**
([its-harsh-here/SkyHigh](https://github.com/its-harsh-here/SkyHigh)).

Same mission — read every METAR, TAF, PIREP, SIGMET, G-AIRMET, CWA and NOTAM
along a route and score the risk — rebuilt from the ground up in how it looks,
how it's organised, and how you run it.

---

## At a glance

| | SkyHigh | NavPort |
|---|---|---|
| **Name** | SkyHigh | NavPort |
| **Backend** | One 1,492-line `app.py`, duplicated verbatim as `main.py` | `backend/` package — config, models, services, routes, telemetry |
| **Frontend** | One 1,535-line `index.html` with inline CSS + inline JS | 4 stylesheets + 16 ES modules, no build step |
| **Theme** | Light only, blue gradients | Light **and** dark, with a toggle that remembers your choice |
| **Typography** | Segoe UI system stack | IBM Plex Sans + IBM Plex Mono |
| **Airport codes** | Bare ICAO codes | ICAO + IATA + name + city, 34k airports offline |
| **Density altitude** | — | Computed at both ends, flagged when significant |
| **Flight rules** | Custom severity only | Standard FAA **VFR / MVFR / IFR / LIFR** per interval |
| **Diversion planning** | — | Live search for usable alternates near the destination |
| **Briefing export** | — | Print / save as PDF, laid out as a document |
| **Route map** | — | Live map with the path drawn in severity colours |
| **Risk display** | Text banner | Animated arc gauge + severity breakdown |
| **Startup** | `pip install` then `python app.py`, by hand | Double-click `run.bat` (Windows) or `run.command` (macOS/Linux) |
| **Docs** | README only | README + `docs/ARCHITECTURE.md` |
| **Server console** | Werkzeug's default request log | Live device / traffic telemetry |

---

## 1. Complete UI rebuild

The old interface was a blue-gradient card layout on a light grey page. The new
one is a designed system rather than a stack of boxes.

**Design language**
- Warm-neutral paper (`#FBFBFA`) with near-black ink, one restrained petrol-blue
  accent. No gradients, no glows, no neon.
- Severity uses muted editorial tones — brick, ochre, forest — instead of
  fluorescent red/amber/green.
- A strict 4pt spacing scale and a consistent 44px rhythm between sections.
- Sections are a heading plus a hairline rule, not nested cards.

**Colour-coded as a warning system**
- Interval and NOTAM rows are washed and outlined by severity, with a 3px
  severity spine down the left edge.
- **Clear conditions stay neutral on purpose** — only abnormal conditions take
  colour, so amber and red actually mean something.
- Severe items carry a slow heartbeat pulse on their status dot.
- Visibility is colour-graded against aviation minimums: red below 1 SM, amber
  below 3 SM.

**A consistent interaction rule: a box means you can press it**
- Status labels (severity, advisories, PIREP counts, NOTAM classification) are
  plain coloured text — they used to look like buttons but weren't.
- METAR / TAF / Pilot-report controls are outlined chips with a rotating
  chevron and a count — they are the only pressable things in a row.

**Dark theme**
- Toggle in the top bar; a single switch with a sliding, slightly overshooting
  knob. Follows your OS until you pick a side, then remembers.
- Charts and map basemap repaint to match, since canvas and map tiles can't
  read CSS variables.

**Motion**
- Radar sweep on the empty state, a scan line while a briefing builds,
  skeleton loaders instead of a spinner, staggered row entrance, hover
  highlights, and corner toasts in place of inline banners.

---

## 2. Flight categories and diversion planning

The previous version scored weather with its own vocabulary (Clear /
Significant / Severe). Useful, but not what a pilot plans in. NavPort now
computes the **standard FAA categories** for every interval and every station:

```
LIFR   ceiling  < 500 ft   or  visibility < 1 sm
IFR    ceiling  < 1000 ft  or  visibility < 3 sm
MVFR   ceiling <= 3000 ft  or  visibility <= 5 sm
VFR    ceiling  > 3000 ft  and visibility > 5 sm
```

Ceiling is the lowest broken/overcast/vertical-visibility layer — few and
scattered layers correctly don't count. The worse of ceiling and visibility
decides the category. The route headline now reads, for example,
*"LIFR — 8 of 17 intervals below VFR"*.

And then the question that actually follows a bad forecast: **where do I go
instead?** `GET /api/alternates/<icao>` searches live METARs around an airport
and returns usable diversions — no worse than the destination and at least
MVFR — ranked best-category-first, then nearest, with distance, true bearing,
compass point, ceiling, visibility and wind for each.

The module also computes headwind/crosswind components for a runway heading,
exposed via `?runway=` on the same endpoint.

---

## 3. Airport identity and density altitude

**Every code now explains itself.** A bundled, public-domain
[OurAirports](https://ourairports.com/data/) extract resolves 34,220
identifiers worldwide to IATA code, airport name, city and country. It is
indexed by `icao_code`, `gps_code` *and* `ident`, because US fields routinely
report weather under an identifier that isn't their formal ICAO code — K12N
and KVES only resolve via the latter two.

The design rule: **the code is the identity, the name is the annotation.**
Pilots scan and speak in codes, so the code never moves or gets replaced.
Where a row has room the name sits beside it; where it doesn't, the code
carries a dotted underline and rolls the meaning down on hover or keyboard
focus. The database is loaded server-side, so the browser pays nothing for it.

**Density altitude** is now computed for departure and destination from
temperature, altimeter setting and field elevation — a standard element of an
FAA preflight briefing, and the number that decides whether the aircraft will
actually perform. It's flagged when it runs more than 2,000 ft above field
elevation. Denver on a 30 °C day reads 8,398 ft, nearly 3,000 ft above the
field.

---

## 4. New features

- **Route map** — Leaflet with keyless Esri basemaps. The flight path is drawn
  segment by segment in its severity colour, with airport markers and
  per-interval condition popups. Degrades to a labelled placeholder offline.
- **Risk gauge** — animated arc showing the risk score, with a Severe /
  Significant / Clear breakdown bar chart.
- **Severity ribbon** — a scrubbable strip of the entire route. Hover for a
  readout, click to jump to that interval.
- **Live server telemetry** — see below.
- **ICAO guidance** — the input fields now state that they take 4-letter ICAO
  codes, with examples and tooltips.
- **Instant PIREP format switching** — decoded and raw text are fetched in one
  request, so the toggle no longer re-hits the API.
- **Printable briefing** — a dedicated print stylesheet turns the dashboard
  into a document: chrome removed, forced light palette, a header with the
  route and generation time, and no row or card split across a page break.
- **Recent routes** — the last five routes are kept locally and re-run in one
  click.

---

## 5. Live terminal telemetry

The server console now reports who is connected and what is going out, instead
of Werkzeug's default log line:

```
┌──────────────────────────────────────────────────────────────────┐
│ NavPort  ·  flight weather intelligence                          │
│ Local    http://127.0.0.1:5000                                   │
│ Network  http://10.71.8.20:5000                                  │
└──────────────────────────────────────────────────────────────────┘

  ● device connected  127.0.0.1  Chrome 130 · Android 14 · Mobile
  17:24:26 GET  /                          200    13.3 KB    73 ms  Chrome 130/Mobile

┌───────────────────────────────────────────────────────────────────┐
│ Traffic  ·  3 devices  ·  5 requests  ·  54.8 KB sent  ·  up 48s  │
├───────────────────────────────────────────────────────────────────┤
│ ● 127.0.0.1  Chrome 130   Android 14     Mobile    2 req  21.0 KB │
│ ● 127.0.0.1  Edge 130     Windows 11/10  Desktop   2 req  20.4 KB │
└───────────────────────────────────────────────────────────────────┘
```

- Announces each new device with browser, OS and form factor (Desktop / Mobile /
  Tablet / CLI), parsed from the User-Agent.
- Per-request line: time, method, path, status, bytes sent, duration, client.
  Static assets are dimmed so real traffic stands out.
- A traffic panel every 20 seconds of activity, and once more on shutdown.
- The banner prints the LAN address to open on a phone or tablet.
- Pure standard library — no new dependencies. Colour is dropped automatically
  when output is piped to a file, when `NO_COLOR` is set, or on terminals
  without ANSI support; box-drawing falls back to ASCII on terminals that
  can't encode it. Reporting is sandboxed so it can never fail a request.

---

## 6. Architecture

**Backend** — one file became a package:

```
backend/
├── config.py          # constants, env-driven host/port/debug
├── models/pirep.py    # PIREP dataclass + raw-text parsing (no I/O)
├── services/          # flight_rules · pirep_service · nlp_processor · weather_service
├── routes/            # flight_routes · pirep_routes (thin blueprints)
└── telemetry.py       # console reporting
```

`main.py` — a verbatim duplicate of `app.py` apart from one comment — was
removed. Route handlers now only validate input and shape JSON; all logic lives
in services.

**Frontend** — native ES modules, so there are real module boundaries but still
no bundler and no build step:

```
frontend/js/
├── main.js       # entry point
├── core/         # api · state · dom · format
├── ui/           # shell · theme · toast
└── views/        # overview · risk · ribbon · map · charts · notams · timeline · pireps
```

Every view owns one card and exposes a single `render*(data)`. Events are
delegated on `data-*` attributes — there is no inline `onclick` anywhere, so
re-rendering never leaks handlers. Untrusted text is escaped before it reaches
`innerHTML`.

**The API contract is unchanged.** Same three endpoints, same request and
response shapes, same data sources.

---

## 7. Running it

One-click launchers for both platforms: **`run.bat`** on Windows and
**`run.command`** on macOS/Linux. Each verifies Python 3.9+ is installed,
creates a virtual environment only if one is missing, installs dependencies
only when `requirements.txt` has actually changed, and starts the server.
Re-running is always safe.

A `.gitattributes` pins `*.command` to LF endings, so the macOS launcher can't
be broken by a CRLF checkout on Windows.

`docs/ARCHITECTURE.md` is new: request flow, module map, and the reasoning
behind the structure.

---

## 8. Bugs fixed along the way

- `main.py` and `app.py` were byte-identical duplicates; one was dead code.
- A stale `python app.py` process could hold port 5000 and answer requests with
  404s — Windows allows several processes to bind the same port.
- Author `display` rules outranked the `[hidden]` attribute, so the PIREP modal
  and skeleton rendered on page load.
- `requestAnimationFrame` never fires in a background tab, which froze every
  animated counter and the risk gauge at `0`.
- A `<body>` background is propagated to the viewport canvas and doesn't
  repaint when the custom property behind it changes — the page background was
  stuck on theme switch. Moved to the root element.
- The top bar's background was hardcoded light, so it stayed pale in dark mode.
- CARTO basemap tiles began requiring an API key; switched to keyless Esri.
- The backend's raw `->` in leg descriptions leaked into the UI; now `→`.
- Static-file responses reported `0 B` in telemetry, because
  `calculate_content_length()` returns `None` in direct-passthrough mode.
- A missing visibility reading rendered as a very alarming `0.00 sm`, because
  `Number(null)` is `0` and passes an `isFinite` check.
- With no observation for a destination, the diversion panel claimed `LIFR` —
  inventing a hazard where it simply had no data. It now says so plainly.
- The diversion lookup lands right behind the briefing's 7-way concurrent
  burst and was being throttled to an empty body; one short retry fixes it.
- Windows lets a second process bind a port that is already being listened on
  rather than refusing it, so two servers both appeared to start while the OS
  quietly routed requests to whichever it liked — leaving the visible console
  silent. Startup now probes the port first and exits with a clear message.
- Telemetry could raise `UnicodeEncodeError` on Windows, where a redirected
  stdout defaults to cp1252 and cannot encode box-drawing glyphs — which threw
  inside `after_request` and took the response down with it.

---

## Unchanged

Weather data still comes from the Aviation Weather Center, with the same
15-day-past to 4-hours-ahead window, the same 15-minute interval analysis, and
the same severity rules. NOTAMs remain deterministic demo data, clearly
labelled as such in every response — real NOTAM feeds need paid or
authenticated access.
