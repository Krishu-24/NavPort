/** Recently analysed routes — pilots fly the same legs over and over. */

import { $, el } from '../core/dom.js';

const KEY = 'navport:recent';
const LIMIT = 5;

function read() {
    try {
        const raw = JSON.parse(localStorage.getItem(KEY) || '[]');
        return Array.isArray(raw) ? raw.filter((r) => r && r.departure && r.destination) : [];
    } catch {
        return [];
    }
}

function write(routes) {
    try {
        localStorage.setItem(KEY, JSON.stringify(routes.slice(0, LIMIT)));
    } catch {
        /* private mode / quota — recents are a convenience, not state we need */
    }
}

export function remember(plan) {
    const entry = {
        departure: plan.departure,
        destination: plan.destination,
        waypoints: plan.waypoints || [],
        cruiseSpeed: plan.cruiseSpeed,
    };

    const id = (r) => `${r.departure}>${r.destination}>${(r.waypoints || []).join(',')}`;
    const rest = read().filter((r) => id(r) !== id(entry));

    write([entry, ...rest]);
    paint();
}

function paint() {
    const host = $('#recent');
    if (!host) return;

    const routes = read();
    host.hidden = routes.length === 0;

    host.replaceChildren(
        el('p', { class: 'eyebrow' }, 'Recent'),
        el('div', { class: 'recent__list' },
            ...routes.map((r) => el('button', {
                class: 'recent__item',
                type: 'button',
                dataset: { route: JSON.stringify(r) },
                title: r.waypoints?.length ? `via ${r.waypoints.join(', ')}` : 'Direct',
            },
                el('span', { class: 'recent__code' }, r.departure),
                el('span', { class: 'recent__arrow' }, '→'),
                el('span', { class: 'recent__code' }, r.destination),
                r.waypoints?.length
                    ? el('span', { class: 'recent__via' }, `+${r.waypoints.length}`)
                    : null,
            )),
        ),
    );
}

/** `onPick` receives the stored plan so the caller can fill the form and run. */
export function initRecent(onPick) {
    paint();

    $('#recent')?.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-route]');
        if (!btn) return;
        try {
            onPick(JSON.parse(btn.dataset.route));
        } catch {
            /* corrupt entry — ignore rather than break the click */
        }
    });
}
