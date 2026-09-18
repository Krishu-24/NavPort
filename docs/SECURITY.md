# Security

What was found, what was done about it, and what is deliberately still open.

This is a student project, not a certified system. The goal was to close the
things that are genuinely exploitable and be explicit about the rest, rather
than to claim a clean bill of health.

---

## How this was tested

`tests/smoke_test.py` is the evidence. It asserts that malformed input gets a
4xx rather than a 500, that error bodies carry no internal detail, that the
security headers are present, and that the rate limiter fires. It runs in CI
on every push.

The first run against the original code: **24 passed, 18 failed.** After the
work below: **65 passed, 0 failed.**

```bash
python tests/smoke_test.py            # against a local server
python tests/smoke_test.py https://your-deployment/
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

**Fix.** An explicit allowlist, confined to `/api/*`. It contains only the
native shell origins (`tauri://localhost`, `capacitor://localhost` and
friends), which genuinely are cross-origin. The web build is same-origin and
needs no CORS at all. Extra origins go in `NAVPORT_CORS_ORIGINS`.

### 3. Exception strings returned to the client

Every handler ended with `return jsonify({'error': f'...{str(e)}'}), 500`,
which hands the caller whatever the exception happened to contain —
filesystem paths, the upstream URL and its parameters, internal hostnames.

**Fix.** A single `Exception` handler logs the full traceback server-side and
returns an opaque `{"error": "Internal server error"}`. Client errors raise
`validation.BadRequest`, whose message is written to be safe to show. The
smoke test asserts that error bodies contain no `Traceback`, no `File "`, no
`backend/` and no `site-packages`.

### 4. Unvalidated identifiers reached the upstream query string

`/api/alternates/<icao>` and `/api/pirep-reports/<station_id>` interpolated
the path segment straight into a request to aviationweather.gov. `requests`
url-encodes parameters, so this was not exploitable as injection, but it was
one refactor away from being so, and it let arbitrary strings out to a third
party.

**Fix.** `backend/validation.py` enforces `^[A-Z0-9]{4}$` on every identifier
before it is used. Nothing that isn't shaped like an ICAO code gets out.

### 5. Bad input produced 500s

An empty POST body, a null identifier, or `cruise_speed: "fast"` all raised
`AttributeError` or `ValueError` and came back as 500s. Beyond being wrong,
each one was a path where an unhandled exception message was returned.

**Fix.** Every field is validated up front. Ten such cases are asserted in
the smoke test; all now return 400 with a message that says what was wrong.

### 6. No rate limiting

One briefing fans out into seven concurrent calls to a free public API. There
was nothing to stop a script turning that into thousands, which is how a
deployment gets blocked by the upstream provider.

**Fix.** A sliding-window limiter in `backend/security.py` — 60 requests and
10 briefings per minute per IP by default. See the caveat below.

### 7. No security headers

**Fix.** `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy`, and HSTS in production.

The CSP allows no inline JavaScript. That required moving the one inline
script into `frontend/js/native.js` rather than weakening the policy —
`'unsafe-inline'` on `script-src` would have made the whole policy close to
decorative. Inline *styles* are still allowed, because Leaflet sets them on
every tile as it positions them; that half of the policy is much less load
bearing.

### 8. Version disclosure

Responses advertised `Server: Werkzeug/3.1.8 Python/3.11.9` — an exact
version pair to match against a CVE list.

**Fix.** `Server: NavPort`. Gunicorn honours the app's header; the
development server needed the handler overriding in `run.py`.

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

**Fix.** All of it is vendored into `frontend/vendor/` and served from our own
origin. `scripts/vendor_assets.py` downloads the pinned versions, verifies
each against a recorded SHA-384 before writing, and runs in CI with `--check`
to confirm the committed copies still match upstream.

This also collapsed the policy. `script-src` and `font-src` are now plain
`'self'` with no host list, so an injected `<script src>` pointing anywhere
at all is refused rather than being weighed against an allowlist. The only
remaining cross-origin request in the whole app is the Esri basemap tile
service in `img-src`, and the smoke test asserts that `index.html` loads no
third-party scripts or styles so this cannot quietly regress.

### 10. Container ran as root

**Fix.** A fixed unprivileged uid/gid (10001), dependencies built in a
separate stage so no compiler ships in the runtime image, `read_only` root
filesystem, `cap_drop: ALL` and `no-new-privileges` in compose. CI asserts
the running container's uid is not 0.

### 11. Thread-unsafe global random state

`simulate_historical_weather` called `random.seed(...)` on the *module-level*
generator. Under a threaded server, two concurrent briefings re-seeded each
other mid-draw, so identical coordinates and times stopped producing
identical weather — destroying the determinism that seeding was there to
provide.

**Fix.** A private `random.Random(seed)` instance per call. Not a security
hole, but a correctness bug that only appears under concurrency, which is
exactly the condition production runs in.

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
smoke test asserts that label is present on all of them, so this cannot
quietly start looking like live data.

### Weather outside the API's real-time window is simulated

Deterministically derived from the nearest real observation. Also labelled.
`docs/ARCHITECTURE.md` covers the reasoning.

### Dependencies are pinned but not automatically updated

`requirements.txt` pins exact versions, which makes builds reproducible and
means a compromised upstream release is not picked up silently. The flip side
is that security patches are not picked up either. Trivy scans the image in
CI and reports HIGH and CRITICAL findings; enabling Dependabot would close
the loop.

---

## Deliberate design decision: weather is never cached offline

The service worker caches the app shell and refuses to cache `/api/*`.

This is a safety decision rather than a technical one. A cached METAR is
indistinguishable on screen from a current one, and ceiling and visibility can
change completely inside the few minutes a cache would happily serve. For a
tool whose output is a go/no-go risk assessment, a stale answer that looks
current is worse than no answer.

So when the network drops, NavPort says so — a persistent banner, and nothing
rendered from cache. `frontend/sw.js` and `frontend/offline.html` both carry
this reasoning inline so it doesn't get "optimised" away later.

---

## Reporting something

This is coursework, not a service with users. If you find something, open an
issue on the repository.
