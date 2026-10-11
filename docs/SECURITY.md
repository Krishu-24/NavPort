# Security

What was found, what was done about it, and what is deliberately still open.

This is a student project, not a certified system. The goal was to close the
things that are genuinely exploitable and be explicit about the rest, rather
than to claim a clean bill of health.

---

## How this was tested

Two end-to-end tests are the evidence, one per service. Both run in CI on
every push, against the development servers and against the Docker containers.

- `backend/tests/api_test.py` asserts that malformed input gets a 4xx rather
  than a 500, that error bodies carry no internal detail, that the API's
  security headers are present, that CORS admits the dashboard and nobody
  else, and that the rate limiter fires.
- `frontend/tests/site_test.py` asserts the dashboard's headers and
  Content-Security-Policy, content types, compression, and that every file the
  service worker needs exists. The frontend workflow also runs it against the
  live site after every deploy.

History: the first run of the original combined smoke test against the
original code was **24 passed, 18 failed**; after the fixes below it was 65
passed. After the dashboard and API were split into two services, the API test
passes **56/56** and the dashboard test **40/40** — and the dashboard test,
pointed at the deployed site before its headers were restored (§12), scored
**31 passed, 9 failed**.

```bash
python backend/tests/api_test.py https://your-api/
python frontend/tests/site_test.py https://your-dashboard/
```

---

## Fixed

### 1. Debug mode defaulted to on — remote code execution

`NAVPORT_DEBUG` defaulted to `true`. The Werkzeug debugger is an interactive
Python console exposed over HTTP; reachable, it is a full shell on the host.
A deployment that simply forgot to set an environment variable was wide open.

**Fix.** Every default in `backend/config.py` is now the safe one, and
production is the default environment. Debug requires *both*
`NAVPORT_ENV=development` and `NAVPORT_DEBUG=true`, so no single omission can
enable it. Local development opts in explicitly.

### 2. `CORS(app)` allowed every origin

The default `flask-cors` configuration sends
`Access-Control-Allow-Origin: *` on every route. Any website could drive this
API using a visitor's browser and IP, spending our upstream quota and
bypassing the rate limit by spreading load across real users.

**Fix.** An explicit allowlist, confined to `/api/*`: the native shell
origins (`tauri://localhost`, `capacitor://localhost` and friends), plus
whatever `NAVPORT_CORS_ORIGINS` names. Since the dashboard moved to its own
host it is cross-origin too, so its exact address has to be in that variable
— and nothing else does. `api_test.py` checks both halves: the dashboard's
origin is granted (including the preflight a JSON `POST` needs), and an
unknown origin gets no `Access-Control-Allow-Origin` at all.

### 3. Exception strings returned to the client

Every handler ended with `return jsonify({'error': f'...{str(e)}'}), 500`,
which hands the caller whatever the exception happened to contain —
filesystem paths, the upstream URL and its parameters, internal hostnames.

**Fix.** A single `Exception` handler logs the full traceback server-side and
returns an opaque `{"error": "Internal server error"}`. Client errors raise
`validation.BadRequest`, whose message is written to be safe to show. The
API test asserts that error bodies contain no `Traceback`, no `File "`, no
`navport/`, no `backend/` and no `site-packages`.

### 4. Unvalidated identifiers reached the upstream query string

`/api/alternates/<icao>` and `/api/pirep-reports/<station_id>` interpolated
the path segment straight into a request to aviationweather.gov. `requests`
url-encodes parameters, so this was not exploitable as injection, but it was
one refactor away from being so, and it let arbitrary strings out to a third
party.

**Fix.** `backend/navport/validation.py` enforces `^[A-Z0-9]{4}$` on every identifier
before it is used. Nothing that isn't shaped like an ICAO code gets out.

### 5. Bad input produced 500s

An empty POST body, a null identifier, or `cruise_speed: "fast"` all raised
`AttributeError` or `ValueError` and came back as 500s. Beyond being wrong,
each one was a path where an unhandled exception message was returned.

**Fix.** Every field is validated up front. Over a dozen such cases are
asserted in the API test; all return 400 (or 405 for the wrong method) with a
message that says what was wrong.

### 6. No rate limiting

One briefing fans out into seven concurrent calls to a free public API. There
was nothing to stop a script turning that into thousands, which is how a
deployment gets blocked by the upstream provider.

**Fix.** A sliding-window limiter in `backend/navport/security.py` — 60 requests and
10 briefings per minute per IP by default. See the caveat below.

### 7. No security headers

**Fix.** `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy`, and HSTS in production.

Each service now sends its own. The API returns only JSON, so its policy
permits nothing: `default-src 'none'; frame-ancestors 'none'`. The dashboard's
policy has to allow its own scripts, the map tiles and the API, and lives in
`frontend/public/staticwebapp.config.json` (see §12).

The dashboard's CSP allows no inline JavaScript. That required moving the one
inline script into `frontend/public/js/native.js` rather than weakening the
policy, and later putting the API's address in its own file
(`js/api-config.js`) rather than an inline `<script>` —
`'unsafe-inline'` on `script-src` would have made the whole policy close to
decorative. Inline *styles* are still allowed, because Leaflet sets them on
every tile as it positions them; that half of the policy is much less load
bearing.

### 8. Version disclosure

Responses advertised `Server: Werkzeug/3.1.8 Python/3.11.9` — an exact
version pair to match against a CVE list.

**Fix.** `Server: NavPort`.

The first version of this fix set the header in the application and assumed
gunicorn would pass it through. It doesn't: gunicorn treats `Server` (like
`Date`) as its own, drops whatever the application set, and writes
`Server: gunicorn` — which is what the deployed API was sending the whole time.
That surfaced only when the API test was tightened to check the header on the
gunicorn container rather than just the development server. Gunicorn's name is
now set in `backend/gunicorn.conf.py`; the development server's handler is
overridden in `backend/wsgi.py`; the dashboard's nginx container sets
`server_tokens off`. Both tests fail if a version number reappears.

### 9. Third-party code loaded from CDNs at runtime

Chart.js and Leaflet came from jsdelivr and unpkg, and the fonts from Google,
with no integrity check. A compromised CDN or a hijacked package could serve
different JavaScript into the page with full access to it.

The first fix was Subresource Integrity — `integrity` and `crossorigin` on
each tag, so the browser refuses a file that doesn't hash to the expected
value. That closed the tampering hole but not the availability one, and
testing the UI across form factors showed why it mattered: on repeated loads
the CDN copy of Leaflet intermittently failed to execute, and the only symptom
was an empty grey panel where the route map should be. No error, no broken
layout, nothing a user would report — just a missing map on a tool whose
entire job is showing weather along a route. SRI cannot help with that, and
neither can a retry: the bundled desktop and mobile apps are expected to open
without a network at all.

**Fix.** All of it is vendored into `frontend/public/vendor/` and served from
the dashboard's own origin. `scripts/vendor_assets.py` downloads the pinned versions, verifies
each against a recorded SHA-384 before writing, and runs in CI with `--check`
to confirm the committed copies still match upstream.

This also collapsed the policy. `script-src` and `font-src` are now plain
`'self'` with no host list, so an injected `<script src>` pointing anywhere
at all is refused rather than being weighed against an allowlist. The only
remaining cross-origin request in the whole app is the Esri basemap tile
service in `img-src` (plus the API in `connect-src`), and the dashboard test
asserts that `index.html` loads no third-party scripts or styles so this cannot
quietly regress.

### 10. Container ran as root

**Fix.** The API image runs as a fixed unprivileged uid/gid (10001), with
dependencies built in a separate stage so no compiler ships in the runtime
image. The dashboard's local nginx image uses the unprivileged variant (uid
101, port 8080, since binding 80 needs root). Both run with a `read_only` root
filesystem, `cap_drop: ALL` and `no-new-privileges` in compose, and CI asserts
that neither running container's uid is 0.

### 11. Thread-unsafe global random state

`simulate_historical_weather` called `random.seed(...)` on the *module-level*
generator. Under a threaded server, two concurrent briefings re-seeded each
other mid-draw, so identical coordinates and times stopped producing
identical weather — destroying the determinism that seeding was there to
provide.

**Fix.** A private `random.Random(seed)` instance per call. Not a security
hole, but a correctness bug that only appears under concurrency, which is
exactly the condition production runs in.

### 12. The dashboard lost its security headers when it moved hosts

Splitting the dashboard out of the Flask app and onto Azure Static Web Apps
quietly removed every protection in §7 from the page itself. Those headers had
been added by the Flask process that served the HTML; Static Web Apps serves
the files directly and only adds three defaults of its own. The live dashboard
had no Content-Security-Policy and no `X-Frame-Options`, and nothing looked
wrong — the page worked exactly as before. The same check found
`manifest.webmanifest` served as `application/octet-stream`, which lets a
browser ignore the manifest and breaks "install as an app".

It was found by inspecting the live response headers after the move, and
confirmed by the new dashboard test: **31 passed, 9 failed** against the
deployed site.

**Fix.** The dashboard's headers, MIME types and cache rules now live with the
dashboard, in `frontend/public/staticwebapp.config.json`, which Static Web
Apps applies directly. The local development server and the nginx container
generate their headers from that same file (`frontend/tools/site.py`), so the
three can't drift apart. The policy's `connect-src` names the API, whose
address differs per environment, so the committed file holds a placeholder
that `site.py configure` fills at deploy time — and the dashboard test fails
if the placeholder ever reaches production unfilled. The frontend workflow
runs that test against the live site after every deploy, so this class of
problem can't come back silently.

---

## Known limitations

Being honest about these is more useful than a clean list.

### The rate limiter is per-process

It holds state in worker memory, so with `WEB_CONCURRENCY=2` and 2 replicas,
a configured limit of 10 is effectively up to 40. The fix is shared state in
Redis, which is neither free nor warranted here. The defaults are set low
enough that the multiplied ceiling is still sane.

It also resets when a worker recycles (`max_requests = 1000`).

### `NAVPORT_TRUST_PROXY` is load-bearing

Behind Azure's ingress the socket peer is the load balancer, so without
trusting `X-Forwarded-For` every client shares one bucket and the limiter
does nothing. Exposed directly, trusting it means any client can spoof its
address and bypass the limiter entirely.

Getting this backwards silently breaks the limiter in either direction. It
defaults to on in production and off in development, which is right for the
documented deployment. [docker-compose.yml](../docker-compose.yml) sets it
**false** (laptop, no proxy). Azure Container Apps must set it **true**
(ingress overwrites `X-Forwarded-For`). **If you ever expose the container
without a proxy in front, set it to `false`.**

### There is no authentication

Every endpoint is public. For a read-only weather tool with no user data that
is a reasonable choice, but it does mean the only protection against abuse is
the rate limiter. Anything storing user data would need real auth first.

### NOTAMs are simulated

Real NOTAM feeds require an authenticated or paid API. The generated ones are
labelled `"source": "Demo Data (Time-Based)"` in every response, and the
API test asserts that label is present on all of them, so this cannot
quietly start looking like live data.

### Weather outside the API's real-time window is simulated

Deterministically derived from the nearest real observation. Also labelled.
`docs/ARCHITECTURE.md` covers the reasoning.

### Dependencies are pinned but not automatically updated

`backend/requirements.txt` pins exact versions, which makes builds
reproducible and means a compromised upstream release is not picked up
silently. The flip side is that security patches are not picked up either: an
audit found three pinned packages carrying published advisories —
Flask-CORS 4.0.0 (CVE-2024-6221), requests 2.31.0 (CVE-2024-35195) and
gunicorn 21.2.0 (CVE-2024-1135) — all since upgraded. Trivy scans the image on
every backend deploy and reports HIGH and CRITICAL findings; enabling
Dependabot would close the loop.

That scan is newer than it looks. The deploy workflow referenced
`aquasecurity/trivy-action@0.28.0`, a tag that does not exist, so GitHub could
not fetch the action and the whole job failed at "Set up job" on every push —
nothing was scanned, and no image was ever published, while the workflow
file read as though both happened. Third-party actions are now pinned to a
commit hash rather than a tag: a tag can be moved or deleted, a commit cannot.

---

## Deliberate design decision: weather is never cached offline

The service worker caches the app shell and refuses to cache `/api/*`.

This is a safety decision rather than a technical one. A cached METAR is
indistinguishable on screen from a current one, and ceiling and visibility can
change completely inside the few minutes a cache would happily serve. For a
tool whose output is a go/no-go risk assessment, a stale answer that looks
current is worse than no answer.

So when the network drops, NavPort says so — a persistent banner, and nothing
rendered from cache. `frontend/public/sw.js` and `frontend/public/offline.html` both carry
this reasoning inline so it doesn't get "optimised" away later.

---

## Reporting something

This is coursework, not a service with users. If you find something, open an
issue on the repository.
