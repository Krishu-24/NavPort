/**
 * Where the API lives.
 *
 * The dashboard and the API are separate services on separate origins, so a
 * relative `/api/...` would ask the static site — or, inside a Tauri or
 * Capacitor webview, the app bundle — for something only the API has. Every
 * build has to be told the API's origin.
 *
 * Resolution order, first match wins:
 *
 *   1. `window.NAVPORT_API_BASE`, set before the app boots by api-config.js
 *      (written per deployment) or by a native shell.
 *   2. `?api=` in the URL, for pointing a dev build at a staging deployment
 *      without rebuilding. Ignored unless the page is itself on localhost, so
 *      a link like `https://navport.example/?api=https://evil.test` cannot
 *      redirect a real user's briefings to somebody else's server.
 *   3. `navport:apiBase` in localStorage, so a choice made once sticks.
 *   4. Same origin — a last resort, for a page served behind a proxy that
 *      also routes /api to the API.
 */

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '']);

/** True when this page is itself running on a developer's machine. */
function isLocalPage() {
    return LOCAL_HOSTS.has(window.location.hostname)
        || window.location.protocol === 'file:';
}

/** Accept only an absolute http(s) origin, and never one with credentials. */
function sanitiseBase(value) {
    if (!value || typeof value !== 'string') return null;

    try {
        const url = new URL(value.trim(), window.location.href);
        if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
        if (url.username || url.password) return null;

        // Keep any path prefix (a reverse proxy may mount the API under one),
        // but drop a trailing slash so joining paths never doubles it.
        return (url.origin + url.pathname).replace(/\/+$/, '');
    } catch {
        return null;
    }
}

function resolveBase() {
    const injected = sanitiseBase(window.NAVPORT_API_BASE);
    if (injected) return injected;

    if (isLocalPage()) {
        const fromQuery = sanitiseBase(new URLSearchParams(window.location.search).get('api'));
        if (fromQuery) {
            try {
                localStorage.setItem('navport:apiBase', fromQuery);
            } catch {
                // Private browsing denies localStorage; the override still
                // applies to this page load.
            }
            return fromQuery;
        }
    }

    try {
        const stored = sanitiseBase(localStorage.getItem('navport:apiBase'));
        if (stored) return stored;
    } catch {
        // Ignore and fall through to same-origin.
    }

    return '';
}

export const API_BASE = resolveBase();

/** True when the app is talking to a server on a different origin. */
export const IS_REMOTE_API = API_BASE !== '' && !API_BASE.startsWith(window.location.origin);

/** Build a full URL for an API path. */
export function apiUrl(path) {
    return API_BASE + path;
}

/**
 * True when running inside one of the native shells rather than a browser tab.
 * The UI uses this to leave room for a phone's status bar and home indicator.
 */
export const IS_NATIVE_SHELL = Boolean(
    window.__TAURI__
    || window.__TAURI_INTERNALS__
    || window.Capacitor
    || window.location.protocol === 'tauri:'
    || window.location.protocol === 'capacitor:',
);

/** True when launched from the home screen or as an installed desktop app. */
export const IS_STANDALONE = Boolean(
    window.matchMedia('(display-mode: standalone)').matches
    || window.matchMedia('(display-mode: window-controls-overlay)').matches
    || window.navigator.standalone,
);
