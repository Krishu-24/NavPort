/** Minimal DOM helpers — keeps view modules free of boilerplate. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Escape untrusted text before it goes anywhere near innerHTML. */
export function esc(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Create an element: el('div', { class: 'x', dataset: { i: 1 } }, ...children) */
export function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);

    for (const [key, value] of Object.entries(props)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class') node.className = value;
        else if (key === 'html') node.innerHTML = value;
        else if (key === 'dataset') Object.assign(node.dataset, value);
        else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
        else node.setAttribute(key, value === true ? '' : value);
    }

    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(child));
    }

    return node;
}

export const show = (node, visible = true) => { node.hidden = !visible; };

/** Read a design token so canvas/JS-drawn colour follows the active theme. */
export const cssVar = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/**
 * Run `fn` on the next frame, or immediately when frames aren't coming —
 * requestAnimationFrame never fires in a background tab, which would otherwise
 * leave entrance animations stuck on their starting values.
 */
export function nextFrame(fn) {
    if (document.hidden) fn();
    else requestAnimationFrame(fn);
}

/** Count a number up to its final value — small touch, big perceived polish. */
export function animateNumber(node, to, { duration = 900, decimals = 0 } = {}) {
    const skip = document.hidden
        || window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (skip) {
        node.textContent = to.toFixed(decimals);
        return;
    }

    const from = 0;
    const start = performance.now();

    const step = (now) => {
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        node.textContent = (from + (to - from) * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
}
