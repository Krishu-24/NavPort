# infra/ — NavPort's Azure setup as code

`main.bicep` describes everything in resource group `rg-navport`:

| Resource | Type | Notes |
|---|---|---|
| `navport-env` | Container Apps environment | express mode, no log storage |
| `navport` | Container App | the API image from Docker Hub, 0.25 vCPU / 0.5 GiB, scales 0–2 |
| `navport-web` | Static Web App | Free plan; content uploaded by the Frontend workflow |
| `navport_budget` | Cost budget | ₹50 a month (normal is about ₹15), email at 50% and 100% actual and 100% forecast |

`main.bicepparam` holds the public values. Two private values are passed at
deploy time and never committed: the read-only Docker Hub token and the email
for budget alerts.

CI compiles `main.bicep` on every push (`.github/workflows/ci.yml`, "Infrastructure
as code compiles cleanly") and fails on any warning.

## Preview a change (changes nothing)

```powershell
az deployment group what-if -g rg-navport -f infra/main.bicep -p infra/main.bicepparam `
  -p dockerHubToken=preview-only alertEmail=you@example.com
```

`what-if` lists what would be created, modified or deleted. Two lines on
`navport-web` (`stableInboundIP`, `trafficSplitting`) are values Azure computes
itself and always show; they are not changes.

## Deploy

```powershell
$sec = Read-Host "navport-azure-pull token" -AsSecureString
$tok = [System.Net.NetworkCredential]::new("", $sec).Password
az deployment group create -g rg-navport -f infra/main.bicep -p infra/main.bicepparam `
  -p dockerHubToken=$tok alertEmail=<your email> --query properties.outputs
Remove-Variable sec, tok
```

The token is typed into a masked prompt, so it is never on screen or in shell
history. A deploy is idempotent: running it again with nothing changed changes
nothing.

## Recreate from nothing

```powershell
az group create -n rg-navport -l centralindia
# then the Deploy command above
```

The API gets a new address in a new environment, so afterwards set the
`API_BASE_URL` repository variable and `corsOrigin` in `main.bicepparam` to the
new addresses, and add the new Static Web App's deployment token as the
`AZURE_STATIC_WEB_APPS_API_TOKEN` secret.

## Why these sizes

Measured on Azure (12–23 October 2026): at most ~260 MB of memory and 0.05 vCPU.
The cost data showed Container Apps charges from 1 October, so the monthly free
grant did not cover this Azure for Students subscription, and every request
wakes a replica that is billed while it runs. 0.25 vCPU / 0.5 GiB, the
smallest size, halves the per-second rate.

## Express mode

In October 2026 Azure automatically migrated `navport-env` to Container Apps
**express**, a fully managed tier for HTTP apps. Express manages scale-down
itself and ignores `scale.cooldownPeriod`, and the app, created before the
migration, has reported its provisioning state as `Failed` since, although
updates still roll out and it serves normally. Recreating the app in the same
environment clears that and keeps the same address:

```powershell
az containerapp delete -n navport -g rg-navport --yes
# then the Deploy command above
```
