/** Formatting + severity vocabulary shared by every view. */

import { cssVar } from './dom.js';

/** Backend severities are 'Clear' | 'Significant' | 'Severe'. */
export const SEVERITY = {
    Clear:       { key: 'ok',   label: 'Clear' },
    Significant: { key: 'warn', label: 'Significant' },
    Severe:      { key: 'crit', label: 'Severe' },
};

/**
 * Colour is resolved from the stylesheet at call time so anything drawn in
 * JS (map polylines, chart bars) stays in step with the active theme.
 */
export function sev(name) {
    const base = SEVERITY[name] || SEVERITY.Clear;
    return { ...base, color: cssVar(`--${base.key}`) };
}

/** 4.8 -> "4h 48m" */
export function flightTime(hours) {
    if (!Number.isFinite(hours)) return '—';
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    return m === 60 ? `${h + 1}h 00m` : `${h}h ${String(m).padStart(2, '0')}m`;
}

/** "23:25 UTC" -> "23:25" */
export const clockOnly = (label = '') => label.replace(' UTC', '');

export function utcNow() {
    return new Date().toUTCString().slice(17, 25);
}

/** ISO or epoch-seconds -> "10 Sep, 19:54 UTC" */
export function stamp(value) {
    const d = toDate(value);
    if (!d) return '—';
    return d.toLocaleString('en-GB', {
        day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
        timeZone: 'UTC', hour12: false,
    }) + ' UTC';
}

/** ISO or epoch-seconds -> "36 min ago" */
export function ago(value) {
    const d = toDate(value);
    if (!d) return '';
    const mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const h = Math.floor(mins / 60);
    return `${h}h ${mins % 60}m ago`;
}

function toDate(value) {
    if (value === null || value === undefined || value === '') return null;
    const raw = String(value);
    const d = /^\d+$/.test(raw)
        ? new Date(Number(raw) * 1000)
        : new Date(raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`);
    return Number.isNaN(d.getTime()) ? null : d;
}

/** FAA flight categories, worst to best. */
export const CATEGORY = {
    LIFR: { key: 'lifr', label: 'LIFR', title: 'Low instrument flight rules' },
    IFR:  { key: 'ifr',  label: 'IFR',  title: 'Instrument flight rules' },
    MVFR: { key: 'mvfr', label: 'MVFR', title: 'Marginal visual flight rules' },
    VFR:  { key: 'vfr',  label: 'VFR',  title: 'Visual flight rules' },
};

export const cat = (name) => CATEGORY[name] || CATEGORY.VFR;

/** Ceiling in feet, or the standard "unlimited" shorthand. */
export const ceiling = (ft) =>
    (ft === null || ft === undefined ? 'Unlimited' : `${Number(ft).toLocaleString()} ft`);

/** The API writes legs as "KJFK -> KORD"; render a real arrow. */
export const place = (text = '') => text.replace(/\s*->\s*/g, ' → ');

/** Visibility comes back as a float like 3.5684387624071725 — nobody needs that. */
export function visibility(value) {
    // Number(null) and Number('') are both 0, which would print a missing
    // reading as a very alarming "0.00 sm". Reject empties before converting.
    if (value === null || value === undefined || value === '') return '—';

    const n = Number(value);
    if (!Number.isFinite(n)) return '—';
    if (n >= 10) return '10+';
    return n < 1 ? n.toFixed(2) : n.toFixed(1);
}

export const round = (n, d = 0) => (Number.isFinite(Number(n)) ? Number(n).toFixed(d) : '—');

/** "Weather: SCT | Visibility: 3.56SM | Wind: 192°/10kt" -> tidy sentence. */
export function condition(text = '') {
    return text
        .replace(/Visibility:\s*([\d.]+)SM/g, (_, v) => `Visibility ${visibility(v)} SM`)
        .replace(/Weather:\s*/g, '')
        .replace(/\s*\|\s*/g, ' · ')
        .trim();
}

/** Default departure input value: 2h ago, formatted for datetime-local. */
export function defaultDeparture() {
    const t = new Date(Date.now() - 2 * 3600 * 1000);
    const utc = new Date(t.getTime() - t.getTimezoneOffset() * 60000);
    return utc.toISOString().slice(0, 16);
}
