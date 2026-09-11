/** Pilot-report modal: decoded ⇄ raw, fetched once per station. */

import { $, $$, el, show } from '../core/dom.js';
import { ago, round } from '../core/format.js';
import { fetchPireps } from '../core/api.js';
import { toast } from '../ui/toast.js';

let station = null;
let reports = [];
let format = 'plain';

function tags(p) {
    const items = [
        p.turbulence && ['Turbulence', p.turbulence],
        p.icing && ['Icing', p.icing],
        p.sky && ['Sky', p.sky],
        Number.isFinite(p.temp_c) && ['Temp', `${round(p.temp_c, 0)}°C`],
        p.remarks && ['Remarks', p.remarks],
    ].filter(Boolean);

    if (!items.length) return null;

    return el('div', { class: 'pirep__tags' },
        ...items.map(([k, v]) => {
            const severe = /SEV|EXTREME|EXTM/i.test(String(v));
            const moderate = /MOD/i.test(String(v));
            const cls = severe ? 'tag tag--crit' : moderate ? 'tag tag--warn' : 'tag tag--quiet';
            return el('span', { class: cls },
                el('b', { class: 'pirep__tagkey' }, k),
                ` ${v}`,
            );
        }),
    );
}

function reportCard(p) {
    const text = format === 'raw' ? (p.raw || '—') : (p.summary || p.raw || '—');

    return el('article', { class: 'pirep' },
        el('div', { class: 'pirep__top' },
            el('span', { class: 'pirep__alt' }, p.altitude_ft_msl ? `${p.altitude_ft_msl.toLocaleString()} ft` : 'Alt n/a'),
            el('span', { class: 'pirep__ac' }, p.aircraft || 'Unknown type'),
            el('span', { class: 'pirep__age' }, ago(p.obs_time || p.receipt_time)),
        ),
        el('p', { class: `pirep__text${format === 'raw' ? ' is-raw' : ''}` }, text),
        format === 'plain' ? tags(p) : null,
    );
}

function paint() {
    const body = $('#pirep-body');

    if (!reports.length) {
        body.replaceChildren(el('div', { class: 'state-msg' },
            el('h3', {}, 'No pilot reports'),
            el('p', {}, `Nothing filed near ${station} within 150 nm in the last 6 hours.`),
        ));
        return;
    }

    body.replaceChildren(...reports.map(reportCard));
}

export async function openPireps(code) {
    station = code;
    format = 'plain';

    $$('.seg__btn', $('#pirep-modal')).forEach((b) => b.classList.toggle('is-active', b.dataset.fmt === 'plain'));
    $('#pirep-title').textContent = `Pilot reports · ${code}`;
    $('#pirep-sub').textContent = 'Searching 150 nm · last 6 hours';
    $('#pirep-body').replaceChildren(el('div', { class: 'state-msg' },
        el('div', { class: 'spinner' }),
        'Fetching pilot reports…',
    ));

    show($('#pirep-modal'), true);

    try {
        // raw=false returns both the raw text and the decoded summary,
        // so the format switch is instant and needs no second request.
        const data = await fetchPireps(code, { raw: false });
        if (station !== code) return;            // a newer request superseded this one

        reports = data.pireps || [];
        $('#pirep-sub').textContent = `${data.count} report${data.count === 1 ? '' : 's'} · 150 nm · last 6 hours`;
        paint();
    } catch (err) {
        $('#pirep-body').replaceChildren(el('div', { class: 'state-msg' },
            el('h3', {}, 'Could not load reports'),
            el('p', {}, err.message),
        ));
        toast(`PIREP lookup failed: ${err.message}`, 'err');
    }
}

export function initPirepModal() {
    const modal = $('#pirep-modal');

    const close = () => { show(modal, false); station = null; };

    modal.addEventListener('click', (e) => {
        if (e.target.closest('[data-close]')) close();

        const fmtBtn = e.target.closest('[data-fmt]');
        if (fmtBtn) {
            format = fmtBtn.dataset.fmt;
            $$('.seg__btn', modal).forEach((b) => b.classList.toggle('is-active', b === fmtBtn));
            paint();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) close();
    });
}
