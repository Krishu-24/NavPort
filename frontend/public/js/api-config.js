/**
 * Where the dashboard finds the NavPort API.
 *
 * The dashboard and the API are two separate services on two different
 * origins — in production an Azure Static Web App and an Azure Container App —
 * so the page has to be told the API's address; a relative fetch('/api/...')
 * would go to the static site, which has no API. See config.js for how this
 * value is used.
 *
 * This committed copy is the local-development default: the API runs on port
 * 8000 of whatever machine served this page. That's 127.0.0.1 on the laptop,
 * and the laptop's LAN address when a phone on the same Wi-Fi opens it.
 *
 * Deployments overwrite this file. The frontend workflow runs
 * `python frontend/tools/site.py configure --api-base <url>`, which replaces it
 * with the deployed API's address and adds that same origin to the page's
 * Content-Security-Policy. The address isn't secret — every browser that loads
 * the page sees it — but it differs per environment, so it belongs to the
 * deployment's configuration rather than to the code.
 *
 * Blocking and non-module in <head>: config.js reads this at import time. An
 * external file rather than an inline script, so the CSP can keep refusing
 * inline JavaScript.
 *
 * A value already set wins: the Tauri desktop shell injects its own at startup
 * (desktop/src-tauri/src/lib.rs).
 */
if (!window.NAVPORT_API_BASE) {
    window.NAVPORT_API_BASE = `${location.protocol}//${location.hostname}:8000`;
}
