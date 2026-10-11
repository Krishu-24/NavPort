/** Topbar route chip + the divided stat row. */

import { $, el, animateNumber, show } from '../core/dom.js';
import { cat, flightTime, sev } from '../core/format.js';

function stat({ label, value, unit, sub, word = false, tone = '', decimals = 0, node = null }) {
    const classes = ['stat__value', word ? 'stat__value--word' : '', tone ? `stat__value--${tone}` : '']
        .filter(Boolean).join(' ');

    const valueNode = node || el('div', { class: classes },
        word ? value : '0',
        unit ? el('span', { class: 'stat__unit' }, unit) : null,
    );

    if (!node && !word) animateNumber(valueNode.firstChild, Number(value), { decimals });

    return el('div', { class: 'stat' },
        el('div', { class: 'stat__label' }, label),
        valueNode,
        sub ? el('div', { class: 'stat__sub' }, sub) : null,
    );
}

function categoryNode(name) {
    const c = cat(name);
    return el('div', { class: 'stat__value' },
        el('span', { class: `cat cat--${c.key} cat--lg`, title: c.title }, c.label),
    );
}

export function renderOverview(data) {
    const { route, flight_segments: legs = [], timeline = [] } = data;
    const worst = sev(route.overall_severity);

    $('#stats').replaceChildren(
        stat({ label: 'Distance', value: Math.round(route.total_distance), unit: 'nm' }),
        stat({ label: 'Flight time', value: flightTime(route.total_flight_time), word: true }),
        stat({ label: 'Cruise', value: route.cruise_speed, unit: 'kts' }),
        stat({
            label: 'Legs',
            value: String(legs.length),
            word: true,
            sub: route.waypoints?.length ? `via ${route.waypoints.join(', ')}` : 'Direct',
        }),
        stat({
            label: 'Worst on route',
            node: categoryNode(route.flight_category),
            sub: route.intervals_below_vfr
                ? `${route.intervals_below_vfr} of ${timeline.length} intervals below VFR`
                : `all ${timeline.length} intervals VFR`,
        }),
        stat({
            label: 'Outlook',
            value: worst.label,
            word: true,
            tone: worst.key,
            sub: `${timeline.length} intervals`,
        }),
    );

    $('#chip-from').textContent = route.departure;
    $('#chip-to').textContent = route.destination;
    $('#chip-meta').textContent = `${Math.round(route.total_distance)} nm · ${flightTime(route.total_flight_time)}`;
    show($('#route-chip'), true);
}
