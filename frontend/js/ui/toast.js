/** Corner toasts — a dot, a line of text, nothing else. */

import { $, el } from '../core/dom.js';

export function toast(message, kind = 'ok', ttl = 5000) {
    const host = $('#toasts');
    if (!host) return;

    const node = el('div', { class: 'toast', role: 'status' },
        el('span', { class: `dot dot--${kind === 'err' ? 'crit' : 'ok'}` }),
        el('span', {}, message),
    );

    host.append(node);

    const dismiss = () => {
        node.classList.add('is-out');
        node.addEventListener('animationend', () => node.remove(), { once: true });
    };

    const timer = setTimeout(dismiss, ttl);
    node.addEventListener('click', () => { clearTimeout(timer); dismiss(); });
}
