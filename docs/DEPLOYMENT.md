# Deploying NavPort (Docker + Azure)

NavPort is two services, each hosted where it is cheapest and each deployed
by its own GitHub Actions workflow:

```
  git push main
      │
      ├─ ci.yml        lint · hash checks · Bicep compile · unit, API and site tests
      │                · build both images and test them running
      │
      ├─ backend.yml   (changes in backend/)
      │     docker buildx  linux/amd64 + linux/arm64
      │     → Docker Hub   docker.io/arnav24sinha/navport-backend:sha-<commit>
      │     → Trivy scan
      │                                   Azure pulls the tag (read-only token)
      │                                              ▼
      │                          Azure Container Apps   navport
      │                          https://navport.<...>.azurecontainerapps.io/api/v1
      │
      ├─ frontend.yml  (changes in frontend/)
      │     write the API address → upload → test the live site
      │                                              ▼
      │                          Azure Static Web Apps  navport-web
      │                          https://<name>.azurestaticapps.net  (dashboard + /docs/)
      │
      └─ apps.yml      (tag v*)  Windows · macOS · Linux installers → GitHub Release
```

Every Azure resource — the Container Apps environment, the API app, the Static
Web App and the cost budget — is defined in [`infra/main.bicep`](../infra/main.bicep).
[infra/README.md](../infra/README.md) has the preview and deploy commands.

---

## 0. Rehearse it in Docker on your laptop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
wait until it says it is running. From the repository root:

```bash
docker compose up --build --wait
python backend/tests/api_test.py
python frontend/tests/site_test.py
docker compose down
```

- `http://localhost:8080` — the dashboard, served by unprivileged nginx
- `http://localhost:8000/api/v1/health` — the API; `"status":"ok"` means the
  image booted, gunicorn is listening and the airport database loaded

The backend runs in production mode with the same limits as the Azure replica
(0.25 vCPU, 512 MB), a read-only filesystem and every Linux capability dropped,
so a memory or permission problem shows up here rather than in the cloud. CI
runs exactly these commands on every push.

### `NAVPORT_TRUST_PROXY` — the one setting that differs

| Where | Value | Why |
|---|---|---|
| `docker compose` | `false` | Nothing sits in front. Trusting `X-Forwarded-For` would let anyone fake an IP and skip the rate limit. |
| Azure Container Apps | `true` | Azure terminates HTTPS and sets that header to the real client. Without it every visitor shares one rate-limit bucket. |

---

## 1. Where the image lives — Docker Hub

The image used to live in Azure Container Registry. Its Basic tier charges
every day whether or not anything is pulled, and in September 2026 it was
₹204 of a ₹240 bill, so it was deleted. Docker Hub stores public images for
free.

Two access tokens (Docker Hub → Account settings → Personal access tokens),
never a password:

| Token | Permission | Stored as |
|---|---|---|
| for GitHub Actions | Read & Write | repository secret `DOCKERHUB_TOKEN` (with variable `DOCKERHUB_USERNAME`) |
| for Azure | Read-only | a secret on the container app, set by the Bicep deploy |

Every build is tagged `sha-<commit>`, and Azure always runs an image by commit,
so the running revision names exactly the code it is running.

---

## 2. Creating the Azure resources

```powershell
az login
az group create -n rg-navport -l centralindia
```

then the **Deploy** command in [infra/README.md](../infra/README.md). It types
the read-only Docker Hub token into a masked prompt, so it never appears on
screen, in shell history or in the repository. Run `what-if` first to see every
change before anything is touched.

What it creates:

| Resource | Settings | Why |
|---|---|---|
| Container Apps environment `navport-env` | express mode, no log storage | No Log Analytics workspace to pay for; `az containerapp logs show --follow` still streams live logs |
| Container app `navport` | 0.25 vCPU, 0.5 GiB, 0–2 replicas, HTTP scaler at 10 concurrent requests, external HTTPS on port 8000 | Smallest size; measured peak was ~260 MB and 0.05 vCPU |
| Static Web App `navport-web` | Free plan | Global hosting, HTTPS, security headers from `staticwebapp.config.json` |
| Budget `navport_budget` | ₹50 a month, email at 50% and 100% actual and 100% forecast | A normal month is about ₹15, so ₹25 already means something unusual; catches it within days |

### Container Apps express

In October 2026 Azure automatically migrated `navport-env` to Container Apps
**express**. Express has a single fixed revision (`navport--latest`), manages
scale-down itself and ignores `scale.cooldownPeriod`. An app created before the
migration reports `Failed` on every update although it keeps serving; deleting
it and running the Bicep deploy again recreates it at the same address. See
[infra/README.md](../infra/README.md#express-mode).

### Settings that matter

| Setting | Value | Reason |
|---|---|---|
| `targetPort` | `8000` | Dockerfile `EXPOSE` / gunicorn bind |
| `minReplicas` | `0` | Scale to zero: no requests, no compute charge |
| `maxReplicas` | `2` | Caps what a traffic spike can cost |
| `NAVPORT_ENV` | `production` | Debugger off, HSTS on, CORS restricted |
| `NAVPORT_CORS_ORIGINS` | the Static Web App's address | The dashboard calls the API from another origin |
| `WEB_CONCURRENCY` | `2` | gunicorn workers per replica |

---

## 3. GitHub settings

Settings → Secrets and variables → Actions. Each workflow job turns itself on
only once its settings exist.

| Name | Kind | Used by |
|---|---|---|
| `DOCKERHUB_USERNAME` | variable | Backend: push the image |
| `DOCKERHUB_TOKEN` | secret | Backend: push the image (Read & Write token) |
| `API_BASE_URL` | variable | Frontend and Build apps: the API address the dashboard and desktop apps call |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | secret | Frontend: upload to the Static Web App (Azure portal → navport-web → Manage deployment token) |
| `AZURE_CONTAINERAPP_NAME`, `AZURE_RESOURCE_GROUP` and the `AZURE_CLIENT_ID` / `TENANT_ID` / `SUBSCRIPTION_ID` secrets | variables, secrets | Backend's optional `deploy` job, which logs in to Azure by OIDC. Not configured yet, so API rollouts are one manual command (below). |

---

## 4. Shipping changes

**Dashboard** — push to `main`. The Frontend workflow uploads it and runs the
47-check site test against the live address.

**API** — push to `main`. The Backend workflow publishes
`sha-<commit>` to Docker Hub; then:

```powershell
az containerapp update --name navport --resource-group rg-navport `
  --image docker.io/arnav24sinha/navport-backend:sha-<commit>
$env:NAVPORT_TEST_ORIGIN = "https://<name>.azurestaticapps.net"
python backend/tests/api_test.py https://navport.<...>.azurecontainerapps.io
```

Also put the new tag in `infra/main.bicepparam`, so the Bicep keeps matching
what is live.

**Desktop apps** — push a version tag:

```bash
git tag -a v2.0.3 -m "NavPort 2.0.3"
git push origin v2.0.3
```

The Build apps workflow builds every installer and creates one draft release
with fixed file names. Publish it on GitHub and tick **Set as the latest
release** — the dashboard's download button links to
`/releases/latest/download/<name>`.

---

## 5. Cost

| Need | Service | Cost |
|---|---|---|
| Image registry | Docker Hub | Free |
| API | Azure Container Apps | Per second while a replica runs; ₹0 with no requests |
| Logs | Live stream only | Free |
| Dashboard | Azure Static Web Apps, Free plan | Free |
| CI/CD, installers | GitHub Actions and Releases (public repository) | Free |

Container Apps has a monthly free grant, but the cost data showed charges from
1 October 2026, so the grant did not cover this Azure for Students
subscription. Automated internet scanners calling the public address around
the clock (about 44 requests a day) kept a replica awake for hours and cost
about ₹82 from 13 to 23 October. Halving the size to 0.25 vCPU / 0.5 GiB halved
the cost of every second it runs. Watch Cost Management → Cost analysis, and
let the budget alert do the rest.

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Dashboard loads but every briefing fails | `API_BASE_URL` or `NAVPORT_CORS_ORIGINS` names the wrong address | Fix the variable / `corsOrigin`, redeploy |
| First request after idle takes several seconds | Scale from zero | Expected; that is what keeps idle cost at zero |
| `az containerapp update` reports `Failed` but the app serves | App predates the express migration | Recreate it (section 2) |
| Requests from your laptop stall but work on a phone | A broken IPv6 path on the local network | Use another network; the API test retries |
| Download button gives 404 | The newest release is not marked latest | Edit the release → Set as the latest release |

---

## Report talking points

- Why two services: each deploys on its own and runs where it is cheapest.
- Why a container: identical runtime on the laptop, in CI and on Azure.
- Why two stages and a non-root user: smaller image, smaller blast radius.
- Why Docker Hub, not Azure Container Registry: the registry was most of the bill.
- Why Bicep: the setup can be reviewed, previewed with what-if and recreated.
- Why min 0 replicas and the smallest size: idle costs nothing, busy costs little.
- Why the health check hits `/api/v1/health`, not the weather API: our liveness,
  not upstream's.
- Why `TRUST_PROXY` is true on Azure and false in compose: who owns
  `X-Forwarded-For`.
