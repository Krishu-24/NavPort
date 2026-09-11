/** Diversion planning — nearby airports that are usable alternates.
 *
 * The briefing tells you the destination is IFR; this answers the question
 * that actually follows: so where do I go instead?
 */

import { $, el, show } from '../core/dom.js';
import { cat, ceiling, visibility } from '../core/format.js';
import { ident } from '../core/idents.js';
import { fetchAlternates } from '../core/api.js';

let loadedFor = null;

function catLabel(name, extra = '') {
    const c = cat(name);
    return el('span', { class: `cat cat--${c.key}${extra}`, title: c.title }, c.label);
}

function altCard(a) {
    const wind = a.wind_dir === null || a.wind_dir === undefined
        ? `${Math.round(a.wind_speed || 0)} kt`
        : `${String(a.wind_dir).padStart(3, '0')}° / ${Math.round(a.wind_speed || 0)}${a.wind_gust ? `G${a.wind_gust}` : ''} kt`;

    return el('article', { class: 'alt', title: a.raw || '' },
        el('div', { class: 'alt__top' },
            el('span', { class: 'alt__code' },
                a.identity?.iata ? `${a.station} / ${a.identity.iata}` : a.station),
            catLabel(a.flight_category),
            el('span', { class: 'alt__dist' }, `${a.distance_nm} nm ${a.compass}`),
        ),
        el('div', { class: 'alt__name' }, a.name || a.station),
        el('div', { class: 'alt__wx' },
            el('span', {}, 'Ceil ', el('b', {}, ceiling(a.ceiling_ft))),
            el('span', {}, 'Vis ', el('b', {}, `${visibility(a.visibility_sm)} sm`)),
        ),
        el('div', { class: 'alt__wx', style: 'margin-top:5px' },
            el('span', {}, 'Wind ', el('b', {}, wind)),
            a.improvement ? el('span', { class: 'alt__better' }, 'better') : null,
        ),
    );
}

function renderResult(data) {
    const host = $('#divert-body');

    host.replaceChildren(
        el('div', { class: 'divert__head' },
            ident(data.station, { className: 'divert__station' }),
            data.flight_category ? catLabel(data.flight_category) : null,
            el('span', { class: 'divert__name' }, data.name || ''),
            el('span', { class: 'divert__note' }, data.observed
                ? `Ceiling ${ceiling(data.ceiling_ft)} · Visibility ${visibility(data.visibility_sm)} sm`
                : 'No current observation for this field'),
        ),
        data.alternates.length
            ? el('div', { class: 'divert__grid' }, ...data.alternates.map(altCard))
            : el('div', { class: 'state-msg' },
                el('h3', {}, 'No usable alternates found'),
                el('p', {}, `Nothing at or above MVFR within ${data.searched_nm} nm.`)),
    );

    $('#divert-tag').textContent = data.alternates.length
        ? `${data.total_found} within ${data.searched_nm} nm · nearest ${data.alternates[0].distance_nm} nm`
        : `none within ${data.searched_nm} nm`;
}

export async function renderAlternates(briefing) {
    const destination = briefing?.route?.destination;
    const section = $('#divert-section');
    if (!destination) return show(section, false);

    show(section, true);

    if (loadedFor === destination) return;   // already showing this airport
    loadedFor = destination;

    $('#divert-tag').textContent = 'searching…';
    $('#divert-body').replaceChildren(el('div', { class: 'state-msg' },
        el('div', { class: 'spinner' }),
        `Looking for alternates near ${destination}…`,
    ));

    try {
        const data = await fetchAlternates(destination, { radius: 200, limit: 8 });
        if (loadedFor !== destination) return;   // a newer route superseded this
        renderResult(data);
    } catch (err) {
        $('#divert-tag').textContent = 'unavailable';
        $('#divert-body').replaceChildren(el('div', { class: 'state-msg' },
            el('h3', {}, 'Could not load alternates'),
            el('p', {}, err.message),
        ));
    }
}

export function resetAlternates() {
    loadedFor = null;
}
