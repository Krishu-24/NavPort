/**
 * Light/dark theme. The stylesheet owns every colour via custom properties,
 * so switching is one attribute — but canvas-drawn things (Chart.js) and the
 * map tiles can't read CSS, so we announce the change for them to redraw.
 */

import { $ } from '../core/dom.js';

const KEY = 'navport:theme';

/** 'light' | 'dark' — resolves the OS preference when nothing is stored. */
export function currentTheme() {
    const stored = localStorage.getItem(KEY);
    if (stored === 'light' || stored === 'dark') return stored;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function paint(theme) {
    document.documentElement.dataset.theme = theme;

    const btn = $('#theme-toggle');
    if (!btn) return;
    const dark = theme === 'dark';
    btn.setAttribute('aria-checked', String(dark));
    btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
}

function setTheme(theme) {
    localStorage.setItem(KEY, theme);
    paint(theme);
    window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
}

export function initTheme() {
    paint(currentTheme());

    // One control: pressing anywhere on the switch flips it.
    $('#theme-toggle')?.addEventListener('click', () => {
        setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    });

    // Track the OS while the user hasn't expressed a preference.
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (!localStorage.getItem(KEY)) {
            const theme = currentTheme();
            paint(theme);
            window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
        }
    });
}
