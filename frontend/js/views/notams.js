/** NOTAMs as hairline-separated list rows. */

import { $, el } from '../core/dom.js';
import { sev, stamp } from '../core/format.js';

function notamRow(n) {
    const s = sev(n.severity);

    return el('article', { class: `row row--${s.key} notam` },
        el('div', { class: 'notam__id' },
            n.airport || '—',
            el('small', {}, n.notam_id || ''),
        ),
        el('div', { class: 'notam__body' },
            el('div', { class: 'notam__top' },
                el('span', { class: `tag tag--sev tag--${s.key}${s.key === 'crit' ? ' tag--alert' : ''}` }, s.label),
                el('span', { class: 'tag tag--label' }, n.classification || '—'),
            ),
            el('p', { class: 'notam__text' }, n.text || '—'),
            el('div', { class: 'notam__meta' },
                el('span', {}, el('b', {}, 'From '), stamp(n.start_time)),
                el('span', {}, el('b', {}, 'Until '), stamp(n.end_time)),
                el('span', {}, n.source || '—'),
            ),
        ),
    );
}

export function renderNotams(data) {
    const notams = data.notams || [];
    const host = $('#notams');

    if (!notams.length) {
        host.replaceChildren(el('div', { class: 'state-msg' }, 'No NOTAMs affecting this route.'));
        $('#notam-tag').textContent = 'None active';
        return;
    }

    host.replaceChildren(...notams.map(notamRow));

    const severe = notams.filter((n) => n.severity === 'Severe').length;
    $('#notam-tag').textContent = severe
        ? `${notams.length} active, ${severe} severe`
        : `${notams.length} active`;
}
