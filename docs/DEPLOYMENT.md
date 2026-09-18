# Deploying NavPort (Docker + Azure)

This is the **deployment** path. NavPort is a Flask app plus a static
frontend. Azure will not run `run.bat`. It runs a **Linux container** built
from the [Dockerfile](../Dockerfile). The public website *is* that container:
it serves `index.html` and `/api/*` from the same origin.

Downloadable Windows/Mac/Android shells and the iPhone home-screen icon are
optional extras. They call this same URL. They are documented in
[desktop/README.md](../desktop/README.md) and are not required to finish
hosting.

```
  your code
      │  docker build  (or docker compose)
      ▼
  image  (a snapshot: Python 3.12 + gunicorn + NavPort)
      │  docker push
      ▼
  ghcr.io  (GitHub Container Registry — free warehouse)
      │  Azure pulls the tag
      ▼
  Azure Container Apps
      │  HTTPS, scale to zero when idle
      ▼
  https://<name>.azurecontainerapps.io
      GET /               → dashboard
      GET /api/health     → {"status":"ok", ...}
```

Do not use Azure App Service **F1**: it cannot run this custom Docker image.
Do not use Azure Container Registry: it has no free tier (~$5/month). Store
the image on **ghcr.io**.

---

## 0. Prove it in Docker on your laptop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
wait until it says it is running. From the `NavPort/` folder (the one that
contains `Dockerfile`):

```bash
docker compose up --build
```

Then open:

- `http://localhost:8000` — the dashboard
- `http://localhost:8000/api/health` — JSON; `"status":"ok"` means the image
  booted, gunicorn is listening, and the airport database loaded

This is the **same image shape Azure will run**: 0.5 CPU, 1 GB RAM,
production env, port 8000. If it works here, memory problems show up on your
machine instead of in the cloud. Stop with `Ctrl+C`.

### What the Dockerfile is doing

Two stages, on purpose.

| Stage | Base | What it is for |
|---|---|---|
| **builder** | `python:3.12-slim` | `pip install` into `/opt/venv`. Compilers and pip stay here and are thrown away. |
| **runtime** | `python:3.12-slim` again | Copies only the venv + `backend/` + `frontend/` + gunicorn. Runs as user `navport` (uid 10001), **not root**. |

- `EXPOSE 8000` / `ENV PORT=8000` — gunicorn binds here. Azure must use
  `--target-port 8000`.
- `HEALTHCHECK` curls `http://127.0.0.1:${PORT}/api/health`. It does **not**
  call aviationweather.gov, so NOAA being down does not look like “our
  container is dead.”
- `CMD gunicorn ... run:app` — production server. Not `python run.py`.

[.dockerignore](../.dockerignore) keeps `.venv`, git, `desktop/`, secrets,
and tests out of the build context.

[docker-compose.yml](../docker-compose.yml) is local rehearsal, not Azure
itself: it maps port 8000, sets `NAVPORT_TRUST_PROXY=false` (no Azure proxy
on your laptop), and caps CPU/RAM to the free replica size.

### `TRUST_PROXY` — the one setting that differs

| Where | `NAVPORT_TRUST_PROXY` | Why |
|---|---|---|
| `docker compose` | `false` | Nothing sits in front. Trusting `X-Forwarded-For` would let anyone fake an IP and skip the rate limit. |
| Azure Container Apps | `true` | Azure terminates HTTPS and sets that header to the real client. Without this, every visitor shares one rate-limit bucket. |

---

## 1. Which Azure service

Azure has several ways to run a container. Only one stays free in a way that
lasts.

| Service | Free allowance | Runs this Docker image? | Verdict |
|---|---|---|---|
| **Container Apps** (Consumption) | 180,000 vCPU-s + 360,000 GiB-s + 2M requests **per month, indefinitely** | Yes | **Use this** |
| App Service **F1** | Forever, but 60 min CPU/day | Linux F1 is **code deploy only**, not custom containers | No |
| App Service **B1** | None (~$13/mo) | Yes | Only if you later want a custom domain and will pay / use student credit |
| Container Instances | Tiny, no scale-to-zero | Yes | Bills while it exists |

**Azure Container Apps, Consumption plan, `minReplicas: 0`.** It pulls your
image, gives you HTTPS, starts a copy on a request, and stops it when idle.

### What the free grant actually buys

The replica is sized at 0.5 vCPU / 1 GiB (same as compose):

```
180,000 vCPU-seconds ÷ 0.5 vCPU = 360,000 seconds ≈ 100 hours awake
360,000 GiB-seconds  ÷ 1 GiB    = 360,000 seconds ≈ 100 hours awake
```

A demo a few hours a week costs nothing. The 2 million requests/month is not
the tight limit — **awake time** is. `minReplicas: 1` (always on) is ~730
hours/month against a 100-hour grant and **will bill**. Do not do that.

### Cold starts

After idle, the first request waits **3–8 seconds** while the container
boots. That is the trade for free. Accept it for a student demo.

[Azure for Students](https://azure.microsoft.com/free/students) ($100,
college email, often no credit card) is a safety net if you misconfigure
always-on. It is separate from the Container Apps grant.

---

## 2. Where the image lives (`ghcr.io`)

Azure cannot see your laptop. The image has to sit in a **registry**.

- **Azure Container Registry** — no free tier, Basic ≈ $5/month. Skip.
- **GitHub Container Registry (`ghcr.io`)** — free and unlimited for
  **public** images. [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
  can push here when you later push `main`. You do not need that workflow to
  deploy by hand.

After the first push: GitHub → Packages → the `navport` package → Package
settings → Change visibility → **Public**. Otherwise Azure cannot pull
without extra credentials.

---

## 3. First deployment (when you are ready to go live)

This section is the Azure create. It is not run from this repo automatically.
You need Docker Desktop (to build/push, or let GitHub Actions do it), an
Azure account, and the Azure CLI.

```bash
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

### Build and push the image (hand path)

```bash
# Token needs write:packages. Username is your GitHub login.
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

docker build -t ghcr.io/YOUR_GITHUB_USERNAME/navport:latest .
docker push ghcr.io/YOUR_GITHUB_USERNAME/navport:latest
```

Then make the package public as above.

### Create the app

```bash
RG=navport-rg
LOCATION=centralindia          # or eastus — pick one near you
APP=navport
IMAGE=ghcr.io/YOUR_GITHUB_USERNAME/navport:latest

az group create --name $RG --location $LOCATION

az containerapp env create \
  --name navport-env \
  --resource-group $RG \
  --location $LOCATION

az containerapp create \
  --name $APP \
  --resource-group $RG \
  --environment navport-env \
  --image $IMAGE \
  --target-port 8000 \
  --ingress external \
  --cpu 0.5 --memory 1.0Gi \
  --min-replicas 0 \
  --max-replicas 2 \
  --env-vars \
      NAVPORT_ENV=production \
      NAVPORT_TRUST_PROXY=true \
      WEB_CONCURRENCY=2 \
  --query properties.configuration.ingress.fqdn -o tsv
```

The last line prints the hostname. Success:

```bash
curl https://<fqdn>/api/health
```

You should see `"status":"ok"` and `"airports_loaded":` a number around
34,000. Opening `https://<fqdn>/` in a browser is the deployed product.

A **resource group** is a folder. Deleting `navport-rg` removes the app and
the environment. Useful at the end of a class.

### Settings that matter

| Setting | Value | Reason |
|---|---|---|
| `--target-port` | `8000` | Dockerfile `EXPOSE` / gunicorn bind |
| `--min-replicas` | `0` | Scale to zero. This is what keeps it free |
| `--max-replicas` | `2` | Caps a traffic spike against the grant |
| `NAVPORT_TRUST_PROXY` | `true` | See the table in §0 |
| `NAVPORT_ENV` | `production` | Debugger off, HSTS on, CORS restricted, telemetry off |

Ingress is HTTPS-only. Azure provides the certificate.

### Updating the image later

```bash
az containerapp update --name $APP --resource-group $RG --image $IMAGE
```

---

## 4. After it is live (optional)

The app is already hardened ([SECURITY.md](SECURITY.md)). Two knobs are
deployment-specific.

**CORS.** Same-origin visitors (the Azure URL in a browser) need no extra
origins. Native shells already have an allowlist in `backend/config.py`.
Only set this if you host the UI somewhere else:

```bash
az containerapp update --name $APP --resource-group $RG \
  --set-env-vars NAVPORT_CORS_ORIGINS=https://navport.example.com
```

**Rate limits.** Defaults are 60 requests and 10 briefings per minute per IP,
to protect aviationweather.gov. Lower them to stretch the compute grant:

```bash
az containerapp update --name $APP --resource-group $RG \
  --set-env-vars NAVPORT_RATE_LIMIT=30 NAVPORT_BRIEFING_RATE_LIMIT=5
```

The limiter is in-process, so the real ceiling is roughly that number ×
`WEB_CONCURRENCY` × replicas. Redis would be the alternative; it is not free
and is not warranted here.

**Budget alert** — free grants do not stop a `minReplicas: 1` mistake:

```bash
az consumption budget create \
  --budget-name navport-guard \
  --amount 1 \
  --time-grain Monthly \
  --category Cost
```

---

## 5. If you outgrow the free grant

Same Docker image, no code changes: Fly.io, Google Cloud Run, Render, or
Hugging Face Spaces (Docker). All take a Dockerfile and `$PORT`, which this
image already honours.

---

## Report talking points

- Why a container: identical runtime on the laptop and on Azure.
- Why two stages and a non-root user: smaller image, smaller blast radius.
- Why gunicorn and port 8000: production WSGI; Azure ingress target.
- Why Container Apps Consumption + min 0: monthly grant, scale to zero, cold
  start as the tradeoff.
- Why ghcr.io not ACR: cost.
- Why healthcheck hits `/api/health` not NOAA: liveness vs upstream weather.
- Why `TRUST_PROXY` is true on Azure and false in compose: who owns
  `X-Forwarded-For`.
