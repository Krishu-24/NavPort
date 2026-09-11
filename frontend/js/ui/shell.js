/** App chrome: UTC clock, off-canvas rail, view switching (empty/loading/results). */

import { $, show } from '../core/dom.js';
import { utcNow } from '../core/format.js';

export function startClock() {
    const node = $('#utc-clock');
    const tick = () => { node.textContent = utcNow(); };
    tick();
    setInterval(tick, 1000);
}

export function initRail() {
    const rail = $('#sidebar');
    const scrim = $('#scrim');

    const open = () => { rail.classList.add('is-open'); show(scrim, true); };
    const close = () => { rail.classList.remove('is-open'); show(scrim, false); };

    $('#menu-btn').addEventListener('click', open);
    $('#sidebar-close').addEventListener('click', close);
    scrim.addEventListener('click', close);
    $('#empty-cta').addEventListener('click', () => {
        if (window.matchMedia('(max-width: 1024px)').matches) open();
        else $('#departure').focus();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });

    return { open, close };
}

/** view: 'empty' | 'loading' | 'results' */
export function setView(view) {
    show($('#empty-state'), view === 'empty');
    show($('#skeleton'), view === 'loading');
    show($('#results'), view === 'results');
}

export function setBusy(busy) {
    const btn = $('#analyze-btn');
    btn.classList.toggle('is-busy', busy);
    btn.disabled = busy;
    btn.querySelector('span').textContent = busy ? 'Analyzing…' : 'Analyze route';
}
