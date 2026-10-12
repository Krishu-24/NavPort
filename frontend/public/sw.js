/**
 * NavPort service worker.
 *
 * This is what makes the installed app open instantly and survive a dead
 * network — and what decides, for an aviation tool, which answer is worse
 * than no answer.
 *
 * The caching strategy is split deliberately:
 *
 *   Vendored libraries, fonts, icons   cache-first
 *   (/vendor/, /assets/)
 *       They only change when their filename does, so serving them from disk
 *       is both correct and the reason a cold start is instant. Since they
 *       are vendored there is no CDN left to revalidate against.
 *
 *   The app's own HTML, CSS and JS     network-first, cache when offline
 *       These change with every deploy, and must change together: new HTML
 *       running last deploy's JavaScript is a broken page, not a stale one.
 *       Online, they always come fresh; offline, the cached copy opens the
 *       app.
 *
 *   /api/* — weather                   NETWORK ONLY. Never cached.
 *       This is the important one. A stale METAR is not a degraded feature,
 *       it is a wrong answer to "is it safe to fly", and it looks exactly
 *       like a right one. Ceilings and visibility can change completely
 *       inside the 5 minutes a cache would happily serve. So when the
 *       network is gone the app says so and shows nothing, rather than
 *       quietly re-serving the last briefing as though it were current.
 */

const VERSION = 'navport-v2.4.0';
const SHELL_CACHE = `${VERSION}-shell`;

const OFFLINE_URL = '/offline.html';

/** Paths whose contents never change without the filename changing too. */
const IMMUTABLE = /^\/(vendor|assets)\//;

/** Everything needed to render the dashboard with no network at all. */
const SHELL_ASSETS = [
    '/',
    OFFLINE_URL,
    '/manifest.webmanifest',
    '/css/tokens.css',
    '/css/layout.css',
    '/css/components.css',
    '/css/dashboard.css',
    '/css/platform.css',
    '/css/print.css',
    '/css/board.css',
    '/js/main.js',
    '/js/native.js',
    '/js/api-config.js',
    '/js/config.js',
    '/js/core/api.js',
    '/js/core/dom.js',
    '/js/core/format.js',
    '/js/core/idents.js',
    '/js/core/state.js',
    '/js/ui/shell.js',
    '/js/ui/theme.js',
    '/js/ui/recent.js',
    '/js/ui/toast.js',
    '/js/ui/offline.js',
    '/js/ui/board.js',
    '/js/ui/download.js',
    '/js/views/overview.js',
    '/js/views/risk.js',
    '/js/views/ribbon.js',
    '/js/views/map.js',
    '/js/views/charts.js',
    '/js/views/notams.js',
    '/js/views/timeline.js',
    '/js/views/alternates.js',
    '/js/views/airfields.js',
    '/js/views/pireps.js',
    '/assets/icons/icon-192.png',
    '/assets/icons/icon-512.png',
    '/assets/icons/apple-touch-icon.png',
    '/assets/icons/favicon-32.png',

    // Vendored libraries and fonts. Without these the app opens offline but
    // with no map and no charts, which is the failure this whole file exists
    // to avoid. The latin-ext font subsets are left out on purpose: they are
    // only fetched if a glyph needs them, and precaching them would add
    // ~130 KB to every install for text this UI does not render.
    '/vendor/leaflet/leaflet.css',
    '/vendor/leaflet/leaflet.js',
    '/vendor/chartjs/chart.umd.min.js',
    '/vendor/fonts/fonts.css',
    '/vendor/fonts/ibm-plex-sans-400-latin.woff2',
    '/vendor/fonts/ibm-plex-sans-500-latin.woff2',
    '/vendor/fonts/ibm-plex-sans-600-latin.woff2',
    '/vendor/fonts/ibm-plex-mono-400-latin.woff2',
    '/vendor/fonts/ibm-plex-mono-500-latin.woff2',
    '/vendor/fonts/ibm-plex-mono-600-latin.woff2',
];

// --------------------------------------------------------------------------
// Install / activate
// --------------------------------------------------------------------------

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        const cache = await caches.open(SHELL_CACHE);

        // Added one at a time rather than with cache.addAll, which rejects the
        // whole batch if any single request fails. One renamed file should not
        // leave the app with no offline support at all.
        await Promise.all(SHELL_ASSETS.map(async (url) => {
            try {
                await cache.add(new Request(url, { cache: 'reload' }));
            } catch {
                console.warn('[sw] could not precache', url);
            }
        }));
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const keep = new Set([SHELL_CACHE]);
        const names = await caches.keys();
        await Promise.all(names.filter((n) => !keep.has(n)).map((n) => caches.delete(n)));

        // Serve navigations from the cache without waiting for a round trip to
        // establish that the page hasn't changed.
        if (self.registration.navigationPreload) {
            await self.registration.navigationPreload.disable();
        }

        await self.clients.claim();
    })());
});

/** Lets the page trigger an update instead of waiting for every tab to close. */
self.addEventListener('message', (event) => {
    if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

// --------------------------------------------------------------------------
// Fetch
// --------------------------------------------------------------------------

self.addEventListener('fetch', (event) => {
    const { request } = event;

    // A service worker can only meaningfully cache GETs; anything else is a
    // mutation and must reach the server.
    if (request.method !== 'GET') return;

    const url = new URL(request.url);

    // Weather is never served from cache. See the note at the top of the file.
    if (url.pathname.startsWith('/api/')) return;

    if (request.mode === 'navigate') {
        event.respondWith(handleNavigation(request));
        return;
    }

    // Basemap tiles are the one remaining cross-origin request. They are left
    // to the browser's own HTTP cache: a tile is immutable for its coordinate
    // so it is safe to reuse, but there are thousands of them and filling the
    // app's cache quota with terrain would eventually evict the shell.
    if (url.origin === self.location.origin) {
        // Vendored libraries, fonts and icons really are immutable — they only
        // change when their filename does — so those stay cache-first. The
        // app's own CSS and JS are not: they change whenever the UI does.
        event.respondWith(
            IMMUTABLE.test(url.pathname)
                ? cacheFirst(request, SHELL_CACHE)
                : networkFirst(request, SHELL_CACHE),
        );
    }
});

/**
 * Navigations try the network first, so a deployed change is picked up on the
 * next launch rather than after the cache happens to expire. The cached shell
 * is the immediate fallback, so being offline still opens the app.
 */
async function handleNavigation(request) {
    const cache = await caches.open(SHELL_CACHE);

    try {
        const response = await fetchWithTimeout(request, 4000);
        if (response && response.ok) {
            const path = new URL(request.url).pathname;
            // Only the dashboard itself is the app shell. Caching every HTML
            // navigation under '/' would let any other page replace it.
            if (path === '/' || path === '') {
                cache.put('/', response.clone());
            }
            return response;
        }
        throw new Error(`HTTP ${response && response.status}`);
    } catch {
        return (await cache.match('/'))
            || (await cache.match(OFFLINE_URL))
            || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
    }
}

/**
 * The network's copy when there is one; the cached copy when there isn't.
 *
 * This used to be stale-while-revalidate: serve the cached file at once and
 * refresh it in the background. Navigations are network-first, though, so the
 * first visit after a deploy got the new index.html together with the old
 * main.js from the cache — and a page whose markup and script disagree. The
 * download button added in 2.0.1 stayed hidden on that visit, because the
 * cached script had never heard of it. Fetching code the same way as the page
 * keeps them from the same deploy. Weather is untouched by this: /api/ still
 * never reaches the cache at all.
 */
async function networkFirst(request, cacheName) {
    const cache = await caches.open(cacheName);
    try {
        const response = await fetchWithTimeout(request, 4000);
        if (response && response.ok) {
            cache.put(request, response.clone());
            return response;
        }
        throw new Error(`HTTP ${response && response.status}`);
    } catch {
        return (await cache.match(request)) || Response.error();
    }
}

async function cacheFirst(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        // Opaque cross-origin responses have status 0 and would poison the
        // cache with an unreadable entry.
        if (response.ok) cache.put(request, response.clone());
        return response;
    } catch (error) {
        if (request.destination === 'document') {
            return (await cache.match(OFFLINE_URL)) || Response.error();
        }
        throw error;
    }
}

/**
 * A request on a captive-portal or dead-but-connected network can hang for the
 * browser's full timeout. Cutting it short is what keeps a cold launch on bad
 * airport wifi from staring at a blank screen.
 */
function fetchWithTimeout(request, ms) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('timeout')), ms);
        fetch(request).then(
            (response) => { clearTimeout(timer); resolve(response); },
            (error) => { clearTimeout(timer); reject(error); },
        );
    });
}
