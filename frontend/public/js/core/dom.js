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
    if (document.hidden) { fn(); return; }

    let ran = false;
    const once = () => { if (!ran) { ran = true; fn(); } };

    requestAnimationFrame(once);

    // Same hazard as animateNumber: a page can report itself visible and still
    // never be handed a frame, which would strand whatever `fn` sets on its
    // starting value — here, a risk gauge stuck reading empty while the figure
    // beside it says 80%. Timers still run in that state. At 50ms a real frame
    // (~16ms) wins the race comfortably, so the transition still animates
    // wherever the page is genuinely painting.
    setTimeout(once, 50);
}

/** Count a number up to its final value — small touch, big perceived polish. */
export function animateNumber(node, to, { duration = 900, decimals = 0 } = {}) {
    const settle = () => { node.textContent = to.toFixed(decimals); };

    // Publish the destination up front. Mid-tween, `textContent` is a lie —
    // anything reading the node before the count-up lands sees a partial
    // figure, and code that reads it at the wrong moment gets "0". The target
    // is known immediately, so expose it immediately and let readers ask for
    // the value rather than race the animation for it.
    const host = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    if (host) host.dataset.value = to.toFixed(decimals);

    const skip = document.hidden
        || window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (skip) {
        settle();
        return;
    }

    const from = 0;
    const start = performance.now();
    let finished = false;

    const step = (now) => {
        if (finished) return;
        const p = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - p, 3);
        node.textContent = (from + (to - from) * eased).toFixed(decimals);
        if (p < 1) requestAnimationFrame(step);
        else finished = true;
    };

    requestAnimationFrame(step);

    // The count-up is decoration; the number itself is data, and it must be
    // right whether or not frames ever arrive. A page can report itself
    // visible and still be starved of rAF — a background or occluded tab, an
    // offscreen iframe, an embedded webview — which used to leave the value
    // frozen at 0 for good. Timers keep running in those states, so this
    // guarantees the final figure lands on time either way.
    setTimeout(() => {
        if (finished) return;
        finished = true;
        settle();
    }, duration);
}
