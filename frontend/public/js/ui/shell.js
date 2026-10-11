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
    const menu = $('#menu-btn');
    const closeBtn = $('#sidebar-close');

    // The rail is a permanent column on desktop and a drawer below 900px.
    // Only the drawer has an open/closed state worth announcing or moving
    // focus for — on desktop the panel is simply always there.
    const isDrawer = () => window.matchMedia('(max-width: 900px)').matches;

    const open = () => {
        rail.classList.add('is-open');
        show(scrim, true);
        menu.setAttribute('aria-expanded', 'true');
        if (isDrawer()) closeBtn.focus();
    };

    const close = () => {
        const wasOpen = rail.classList.contains('is-open');
        rail.classList.remove('is-open');
        show(scrim, false);
        menu.setAttribute('aria-expanded', 'false');
        // Hand focus back to the control that opened the drawer, but only if
        // it is still inside the drawer we just closed — otherwise this would
        // yank the caret off whatever the user has since moved to.
        if (wasOpen && isDrawer() && rail.contains(document.activeElement)) menu.focus();
    };

    menu.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
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
