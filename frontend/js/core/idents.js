/**
 * Airport identity rendering.
 *
 * Design rule: **the code is the identity, the name is the annotation.**
 * Pilots scan and speak in codes, so the code always stays primary and never
 * moves or gets replaced. Where a row has room, the name sits beside it as
 * quiet secondary text. Where it doesn't, the code carries a dotted underline
 * and reveals `IATA · Name · City` on hover or keyboard focus.
 *
 * The reveal is CSS-only (opacity + translateY), so it works without JS and
 * respects prefers-reduced-motion.
 */

import { el } from './dom.js';

let registry = {};

/** Store the identity map that came back with a briefing. */
export function loadIdentities(map) {
    registry = map || {};
}

export function identity(code) {
    if (!code) return null;
    return registry[String(code).toUpperCase()] || null;
}

/** "JFK · John F. Kennedy International Airport · New York, US" */
export function fullName(code) {
    const a = identity(code);
    if (!a || !a.name) return null;

    const place = [a.city, a.country].filter(Boolean).join(', ');
    return [a.iata, a.name, place].filter(Boolean).join(' · ');
}

/**
 * An airport code that explains itself on hover/focus.
 * Falls back to plain text when the code isn't in the database.
 */
export function ident(code, { className = '' } = {}) {
    const text = (code || '—').toUpperCase();
    const a = identity(code);

    if (!a || !a.name) {
        return el('span', { class: `ident ident--plain ${className}`.trim() }, text);
    }

    const place = [a.city, a.country].filter(Boolean).join(', ');

    return el('span', {
        class: `ident ${className}`.trim(),
        tabindex: '0',
        role: 'button',
        'aria-label': `${text}. ${fullName(code)}`,
    },
        el('span', { class: 'ident__code' }, text),
        el('span', { class: 'ident__pop', 'aria-hidden': 'true' },
            a.iata ? el('span', { class: 'ident__iata' }, a.iata) : null,
            el('span', { class: 'ident__name' }, a.name),
            place ? el('span', { class: 'ident__place' }, place) : null,
        ),
    );
}

/** Code plus its name as persistent secondary text, for roomier layouts. */
export function identLine(code) {
    const a = identity(code);
    return el('span', { class: 'ident-line' },
        el('span', { class: 'ident-line__code' }, (code || '—').toUpperCase()),
        a?.iata ? el('span', { class: 'ident-line__iata' }, a.iata) : null,
        a?.name ? el('span', { class: 'ident-line__name' }, a.name) : null,
    );
}
