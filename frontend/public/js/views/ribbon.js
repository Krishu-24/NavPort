/** Severity ribbon — a scrubbable strip of the whole route, linked to the timeline. */

import { $, el } from '../core/dom.js';
import { clockOnly, condition, place, sev } from '../core/format.js';

let entries = [];
let tip = null;

export function renderRibbon(data) {
    const timeline = data.timeline || [];
    entries = timeline;

    const host = $('#ribbon');

    host.replaceChildren(...timeline.map((item, i) => {
        const s = sev(item.severity);
        return el('button', {
            class: `rib rib--${s.key}`,
            type: 'button',
            style: `animation-delay:${Math.min(i * 20, 380)}ms`,
            dataset: { index: String(i) },
            'aria-label': `Interval ${i + 1}: ${s.label}`,
        });
    }));

    const counts = timeline.reduce((acc, i) => {
        acc[i.severity] = (acc[i.severity] || 0) + 1;
        return acc;
    }, {});

    $('#ribbon-tag').textContent = [
        counts.Severe ? `${counts.Severe} severe` : null,
        counts.Significant ? `${counts.Significant} significant` : null,
        counts.Clear ? `${counts.Clear} clear` : null,
    ].filter(Boolean).join(' · ') || '—';

    const first = timeline[0];
    const mid = timeline[Math.floor(timeline.length / 2)];
    const last = timeline[timeline.length - 1];

    $('#ribbon-axis').replaceChildren(
        el('span', {}, first ? clockOnly(first.start_time_local) : ''),
        el('span', {}, mid ? clockOnly(mid.start_time_local) : ''),
        el('span', {}, last ? clockOnly(last.end_time_local) : ''),
    );
}

function showTip(rib) {
    const item = entries[Number(rib.dataset.index)];
    if (!item) return;

    const s = sev(item.severity);
    hideTip();

    tip = el('div', { class: 'rib-tip' },
        el('div', { class: 'rib-tip__top' },
            el('span', { class: `dot dot--${s.key}` }),
            `${clockOnly(item.start_time_local)} – ${clockOnly(item.end_time_local)}`,
        ),
        el('div', { class: 'rib-tip__body' },
            place(item.location_description || ''),
            el('br'),
            condition(item.conditions?.condition || ''),
        ),
    );

    document.body.append(tip);

    const r = rib.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const left = Math.min(Math.max(8, r.left + r.width / 2 - t.width / 2), window.innerWidth - t.width - 8);
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, r.top - t.height - 8)}px`;
}

function hideTip() {
    tip?.remove();
    tip = null;
}

/** Wire ribbon <-> timeline cross-highlighting (delegated, bound once). */
export function initRibbonLink() {
    const host = $('#ribbon');

    const setActive = (index, on) => {
        document.querySelector(`.tl[data-index="${index}"]`)?.classList.toggle('is-active', on);
        host.querySelector(`.rib[data-index="${index}"]`)?.classList.toggle('is-active', on);
    };

    host.addEventListener('mouseover', (e) => {
        const rib = e.target.closest('.rib');
        if (!rib) return;
        setActive(rib.dataset.index, true);
        showTip(rib);
    });

    host.addEventListener('mouseout', (e) => {
        const rib = e.target.closest('.rib');
        if (!rib) return;
        setActive(rib.dataset.index, false);
        hideTip();
    });

    host.addEventListener('click', (e) => {
        const rib = e.target.closest('.rib');
        if (!rib) return;
        const row = document.querySelector(`.tl[data-index="${rib.dataset.index}"]`);
        row?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        row?.classList.add('is-active');
        setTimeout(() => row?.classList.remove('is-active'), 1800);
    });

    window.addEventListener('scroll', hideTip, { passive: true });
}
