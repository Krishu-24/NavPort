/** Interval rows with show/hide raw METAR & TAF panels and PIREP access. */

import { $, el } from '../core/dom.js';
import { clockOnly, condition, place, round, sev, visibility } from '../core/format.js';
import { openPireps } from './pireps.js';

const CHEV = '<path d="M2.5 4l3.5 3.5L9.5 4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';

function metric(value, label, tone = '') {
    return el('div', { class: 'metric' },
        el('div', { class: `metric__v${tone ? ` metric__v--${tone}` : ''}` }, value),
        el('div', { class: 'metric__l' }, label),
    );
}

/** Visibility is a hard minimum, so the number itself carries the warning. */
function visTone(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return '';
    if (n < 1) return 'crit';
    if (n < 3) return 'warn';
    return '';
}

function observation(obs) {
    return el('div', { class: 'obs' },
        el('div', { class: 'obs__top' },
            el('span', { class: 'obs__station' }, obs.station || '—'),
            el('span', { class: 'obs__dist' }, `${round(obs.distance, 0)} nm`),
        ),
        obs.raw ? el('pre', { class: 'obs__raw' }, obs.raw) : null,
        obs.nlp ? el('p', { class: 'obs__nlp' }, obs.nlp) : null,
    );
}

function panel(kind, title, list) {
    return el('div', { class: 'panel', hidden: true, dataset: { panelBody: kind } },
        el('div', { class: 'panel__head' }, `${title} — ${list.length} station${list.length === 1 ? '' : 's'}`),
        ...list.map(observation),
    );
}

function toggle(kind, label, count) {
    return el('button', {
        class: 'toggle',
        type: 'button',
        dataset: { panel: kind },
        'aria-expanded': 'false',
    },
        el('svg', { class: 'toggle__chev', viewBox: '0 0 12 12', html: CHEV }),
        label,
        el('span', { class: 'toggle__n' }, String(count)),
    );
}

function row(item, index) {
    const s = sev(item.severity);
    const c = item.conditions || {};
    const raw = item.raw_data || {};
    const metars = raw.metars || [];
    const tafs = raw.tafs || [];
    const hazards = c.hazards || [];
    const station = c.nearest_station && c.nearest_station !== 'Unknown' ? c.nearest_station : null;

    // Status sits with the location; advisories get their own line below.
    const status = el('span', {
        class: `tag tag--sev tag--${s.key}${s.key === 'crit' ? ' tag--alert' : ''}`,
    }, s.label);

    const alertTone = s.key === 'crit' ? 'crit' : 'warn';
    const alerts = [
        ...hazards.map((h) => el('span', { class: `tag tag--${alertTone}` }, h)),
        c.pirep_count
            ? el('span', { class: 'tag tag--quiet' }, `${c.pirep_count} pilot report${c.pirep_count === 1 ? '' : 's'} nearby`)
            : null,
    ].filter(Boolean);

    const toggles = [
        metars.length ? toggle('metars', 'METAR', metars.length) : null,
        tafs.length ? toggle('tafs', 'TAF', tafs.length) : null,
        station ? el('button', { class: 'toggle', type: 'button', dataset: { pirep: station } },
            'Pilot reports', el('span', { class: 'toggle__n' }, station)) : null,
    ].filter(Boolean);

    const panels = [
        metars.length ? panel('metars', 'Surface observations', metars) : null,
        tafs.length ? panel('tafs', 'Terminal forecasts', tafs) : null,
    ].filter(Boolean);

    const gust = Number(item.wind_gust) || 0;

    return el('article', {
        class: `row row--${s.key} tl`,
        style: `animation-delay:${Math.min(index * 22, 400)}ms`,
        dataset: { index: String(index) },
    },
        el('div', { class: 'tl__main' },
            el('div', { class: 'tl__time' },
                clockOnly(item.start_time_local),
                el('small', {}, clockOnly(item.end_time_local)),
            ),
            el('div', { class: 'tl__body' },
                el('div', { class: 'tl__head' },
                    el('span', { class: 'tl__loc' }, place(item.location_description) || '—'),
                    status,
                ),
                el('div', { class: 'tl__cond' }, condition(c.condition || '')),
                alerts.length ? el('div', { class: 'tl__alerts' }, ...alerts) : null,
                c.natural_language ? el('div', { class: 'tl__note' }, c.natural_language) : null,
            ),
            el('div', { class: 'tl__metrics' },
                metric(visibility(item.visibility), 'sm vis', visTone(item.visibility)),
                metric(`${Math.round(Number(item.wind_speed) || 0)}${gust ? `G${Math.round(gust)}` : ''}`, 'kt wind'),
            ),
        ),
        toggles.length ? el('div', { class: 'tl__toggles' }, ...toggles) : null,
        panels.length ? el('div', { class: 'tl__panels' }, ...panels) : null,
    );
}

export function renderTimeline(data) {
    const timeline = data.timeline || [];
    $('#timeline').replaceChildren(...timeline.map(row));
    $('#timeline-tag').textContent = `${timeline.length} intervals, 15 min each`;
}

/** Delegated interactions — bound once at boot, survives every re-render. */
export function initTimeline() {
    $('#timeline').addEventListener('click', (e) => {
        const pirepBtn = e.target.closest('[data-pirep]');
        if (pirepBtn) {
            openPireps(pirepBtn.dataset.pirep);
            return;
        }

        const btn = e.target.closest('[data-panel]');
        if (!btn) return;

        const card = btn.closest('.tl');
        const body = card.querySelector(`[data-panel-body="${btn.dataset.panel}"]`);
        if (!body) return;

        const open = body.hidden;
        body.hidden = !open;
        btn.classList.toggle('is-on', open);
        btn.setAttribute('aria-expanded', String(open));
    });
}
