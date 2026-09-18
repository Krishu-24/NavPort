/**
 * Service worker registration, connection state and the install prompt.
 *
 * The connection banner is not decoration. Weather is never served from cache
 * (see `sw.js`), so when the network drops the dashboard keeps displaying the
 * last briefing it rendered — which is now of unknown age. Saying so plainly,
 * and stamping the briefing with the time it was pulled, is what keeps a stale
 * screen from being read as a current one.
 */

import { $, el } from '../core/dom.js';
import { IS_NATIVE_SHELL } from '../config.js';
import { toast } from './toast.js';

let banner = null;
let installEvent = null;

// --------------------------------------------------------------------------
// Connection banner
// --------------------------------------------------------------------------

function ensureBanner() {
    if (banner) return banner;

    banner = el('div', {
        class: 'conn',
        role: 'status',
        'aria-live': 'polite',
        hidden: true,
    });
    document.body.prepend(banner);
    return banner;
}

function showOffline() {
    const node = ensureBanner();
    node.className = 'conn conn--off';
    node.replaceChildren(
        el('span', { class: 'dot dot--crit' }),
        el('span', {}, 'Offline — weather shown was last loaded earlier and may be out of date.'),
    );
    node.hidden = false;
    document.body.classList.add('is-offline');
}

function showOnline() {
    document.body.classList.remove('is-offline');
    if (!banner || banner.hidden) return;

    banner.className = 'conn conn--on';
    banner.replaceChildren(
        el('span', { class: 'dot dot--ok' }),
        el('span', {}, 'Back online'),
    );

    setTimeout(() => { if (banner) banner.hidden = true; }, 2600);
}

/**
 * `navigator.onLine` only reports whether a network interface is up, so it is
 * true on wifi with no route to the internet. A cheap same-origin probe is
 * what distinguishes "connected" from "actually reachable".
 */
async function isReachable() {
    if (!navigator.onLine) return false;

    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/health', { cache: 'no-store', signal: controller.signal });
        clearTimeout(timer);
        return res.ok;
    } catch {
        return false;
    }
}

async function recheck() {
    if (await isReachable()) showOnline();
    else showOffline();
}

// --------------------------------------------------------------------------
// Service worker
// --------------------------------------------------------------------------

function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return;

    // Inside a native shell the assets are already local, so a service worker
    // adds a second cache layer with nothing to gain. It also can't register
    // over a custom scheme.
    if (IS_NATIVE_SHELL || window.location.protocol === 'file:') return;

    window.addEventListener('load', async () => {
        try {
            const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });

            // A newly installed worker sits in "waiting" until every tab of the
            // app is closed — not merely reloaded. Nothing here ever told it to
            // take over, so the toast below was asking for a reload that could
            // not deliver the update it promised. Handing it SKIP_WAITING and
            // reloading once it has control makes that promise true.
            let reloading = false;
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                if (reloading) return;
                reloading = true;
                window.location.reload();
            });

            const activate = (worker) => worker.postMessage('SKIP_WAITING');

            if (registration.waiting && navigator.serviceWorker.controller) {
                activate(registration.waiting);
            }

            registration.addEventListener('updatefound', () => {
                const incoming = registration.installing;
                if (!incoming) return;

                incoming.addEventListener('statechange', () => {
                    // `controller` is null on the very first install, which is
                    // not an update and should not prompt anyone.
                    if (incoming.state === 'installed' && navigator.serviceWorker.controller) {
                        toast('Updating to the latest version…', 'ok', 4000);
                        activate(incoming);
                    }
                });
            });
        } catch (error) {
            console.warn('[sw] registration failed', error);
        }
    });
}

// --------------------------------------------------------------------------
// Install prompt
// --------------------------------------------------------------------------

function trackInstallPrompt() {
    window.addEventListener('beforeinstallprompt', (event) => {
        // Keep the event so the prompt can be raised from our own button at a
        // sensible moment, rather than the browser's mini-infobar.
        event.preventDefault();
        installEvent = event;
        document.body.classList.add('can-install');
    });

    window.addEventListener('appinstalled', () => {
        installEvent = null;
        document.body.classList.remove('can-install');
    });
}

/** True when the browser is willing to install the app right now. */
export function canInstall() {
    return installEvent !== null;
}

/** Raise the native install prompt. Returns true when the user accepted. */
export async function promptInstall() {
    if (!installEvent) return false;

    installEvent.prompt();
    const { outcome } = await installEvent.userChoice;
    installEvent = null;
    document.body.classList.remove('can-install');
    return outcome === 'accepted';
}

// --------------------------------------------------------------------------

export function initConnection() {
    registerServiceWorker();
    trackInstallPrompt();

    window.addEventListener('online', recheck);
    window.addEventListener('offline', showOffline);

    // Coming back from a backgrounded app is the most likely moment for the
    // connection to have changed underneath us.
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) recheck();
    });

    if (!navigator.onLine) showOffline();
}
