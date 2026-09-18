/** Split-flap board layer. Theme, clock and briefing come from /js/main.js. */

const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$<>#/+&→';
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const running = new Set();

function clearRunning() {
    running.forEach((id) => {
        window.clearInterval(id);
        window.clearTimeout(id);
    });
    running.clear();
}

function makeCell(ch) {
    const cell = document.createElement('span');
    const gap = ch === ' ';
    const colon = ch === ':';
    cell.className = 'board__cell'
        + (gap ? ' board__cell--gap' : '')
        + (colon ? ' board__cell--colon' : '');
    cell.dataset.target = ch;
    cell.textContent = reduceMotion || gap || colon ? ch : ' ';
    return cell;
}

/**
 * Every character is its own flex item, so an unguarded board wraps *inside*
 * a word on a narrow screen — "BRIEFING" breaking as "BRIEFIN / G". Cells are
 * grouped into non-wrapping words, and only the spaces between them are break
 * opportunities, which is how a real board reads.
 */
function mountBoard(el) {
    const text = (el.dataset.board || el.textContent || '').toUpperCase();
    el.dataset.board = text;
    el.replaceChildren();

    let word = null;
    for (const ch of text) {
        if (ch === ' ') {
            word = null;                       // the space itself is the break point
            el.append(makeCell(ch));
            continue;
        }
        if (!word) {
            word = document.createElement('span');
            word.className = 'board__word';
            el.append(word);
        }
        word.append(makeCell(ch));
    }
}

function flipCell(cell, to) {
    cell.classList.remove('is-flip', 'is-set');
    void cell.offsetWidth;
    cell.textContent = to;
    cell.classList.add('is-flip');
}

function playBoard(el, stagger = 0) {
    const cells = [...el.querySelectorAll('.board__cell')];
    cells.forEach((cell, i) => {
        const target = cell.dataset.target;
        if (target === ' ' || target === ':') return;
        if (reduceMotion) {
            cell.textContent = target;
            cell.classList.add('is-set');
            return;
        }
        const cycles = 8 + (i % 7);
        const start = stagger + i * 52;
        const timeoutId = window.setTimeout(() => {
            let n = 0;
            const id = window.setInterval(() => {
                n += 1;
                flipCell(cell, GLYPHS[(Math.random() * GLYPHS.length) | 0]);
                if (n >= cycles) {
                    window.clearInterval(id);
                    running.delete(id);
                    flipCell(cell, target);
                    cell.classList.remove('is-flip');
                    cell.classList.add('is-set');
                }
            }, 40);
            running.add(id);
        }, start);
        running.add(timeoutId);
    });
}

function playIn(root, staggerBase = 0) {
    if (!root) return;
    const boards = [...root.querySelectorAll('.board')].filter(
        (el) => !el.classList.contains('board--clock'),
    );
    boards.forEach((el, i) => {
        mountBoard(el);
        playBoard(el, staggerBase + i * 70);
    });
}

function playVisible() {
    playIn(document.querySelector('.topbar'));
    playIn(document.getElementById('empty-state'), 80);
}

function watchResults() {
    const results = document.getElementById('results');
    if (!results) return;

    const run = () => {
        playIn(results, 0);
        enhanceChip();
        enhanceRisk();
        // Every value is readable the moment it is rendered, so the whole
        // board flips together. This used to hold the counting stats back
        // ~920ms to let their tween finish first, which made the display
        // hostage to a timer race it could lose.
        enhanceStats();
        enhanceGauge();
    };

    new MutationObserver(() => {
        if (!results.hidden) run();
    }).observe(results, { attributes: true, attributeFilter: ['hidden'] });
}

function boardFromText(text, klass) {
    const board = document.createElement('span');
    board.className = `board ${klass}`.trim();
    board.dataset.board = String(text || '').trim().toUpperCase();
    return board;
}

function replaceWithBoard(el, klass, text) {
    if (!el || el.querySelector(':scope > .board')) return;
    const value = (text ?? el.textContent ?? '').trim();
    if (!value || value === '—' || value === '-') return;
    const board = boardFromText(value, klass);
    el.replaceChildren(board);
    mountBoard(board);
    playBoard(board, 0);
}

function enhanceStats() {
    document.querySelectorAll('#stats .stat__value').forEach((el) => {
        if (el.querySelector(':scope > .board')) return;
        const unit = el.querySelector('.stat__unit');
        const cat = el.querySelector('.cat');
        let text;
        if (cat) {
            text = cat.textContent.trim();
        } else if (el.dataset.value) {
            // A counting stat: take the published target, never the digits
            // currently on screen, which are mid-tween (and are "0" outright
            // when frames aren't arriving).
            text = el.dataset.value;
        } else {
            const clone = el.cloneNode(true);
            clone.querySelectorAll('.stat__unit').forEach((n) => n.remove());
            text = clone.textContent.trim();
        }
        if (!text) return;
        const board = boardFromText(text, 'board--stat');
        if (cat) {
            cat.classList.forEach((c) => {
                if (c.startsWith('cat--')) board.classList.add(c);
            });
        }
        const next = [board];
        if (unit) next.push(unit);
        el.replaceChildren(...next);
        mountBoard(board);
        playBoard(board, 0);
    });
}

function enhanceRisk() {
    replaceWithBoard(document.getElementById('risk-level'), '');
}

function enhanceGauge() {
    const pct = document.querySelector('.gauge__pct');
    if (!pct || pct.querySelector(':scope > .board')) return;
    const shown = pct.childNodes[0]?.textContent || pct.textContent || '';
    const text = (pct.dataset.value || shown).replace(/[^\d]/g, '');
    if (!text) return;
    const board = boardFromText(text, 'board--stat');
    const sup = pct.querySelector('sup');
    const next = [board];
    if (sup) next.push(sup);
    pct.replaceChildren(...next);
    mountBoard(board);
    playBoard(board, 0);
}

function enhanceChip() {
    replaceWithBoard(document.getElementById('chip-from'), 'board--chip');
    replaceWithBoard(document.getElementById('chip-to'), 'board--chip');
    const dash = document.getElementById('chip-dash');
    if (dash && !dash.querySelector('.board')) {
        dash.textContent = '→';
        replaceWithBoard(dash, 'board--arrow', '→');
    }
}

/**
 * HH:MM:SS, or HH:MM where the topbar is too tight to afford the seconds.
 *
 * On a phone the bar is a fixed budget shared with the route chip, and the
 * seconds were spending ~25px of it — enough that "KJFK → KLAX" was being
 * clipped to "KJFK → KLA". Which airports you are looking at outranks the
 * least significant digits of a clock, and the hour and minute are what a
 * TAF validity window is actually read against.
 *
 * initClock's tick remounts the board whenever the character count changes,
 * so crossing this breakpoint re-lays the clock out on its own.
 */
function utcStamp() {
    const iso = new Date().toISOString();
    const tight = window.matchMedia('(max-width: 430px)').matches;
    return iso.slice(11, tight ? 16 : 19);
}

function flipDigit(cell, to) {
    if (reduceMotion) {
        cell.textContent = to;
        cell.classList.add('is-set');
        return;
    }
    let n = 0;
    const cycles = 4;
    const id = window.setInterval(() => {
        n += 1;
        flipCell(cell, String((Math.random() * 10) | 0));
        if (n >= cycles) {
            window.clearInterval(id);
            running.delete(id);
            flipCell(cell, to);
            cell.classList.remove('is-flip');
            cell.classList.add('is-set');
        }
    }, 42);
    running.add(id);
}

function initClock() {
    const board = document.getElementById('utc-board');
    if (!board) return;
    board.dataset.board = utcStamp();
    mountBoard(board);
    playBoard(board, 0);

    const tick = () => {
        const next = utcStamp();
        const cells = [...board.querySelectorAll('.board__cell')];
        if (cells.length !== next.length) {
            board.dataset.board = next;
            mountBoard(board);
            playBoard(board, 0);
            return;
        }
        [...next].forEach((ch, i) => {
            const cell = cells[i];
            if (!cell || cell.dataset.target === ch) return;
            cell.dataset.target = ch;
            if (ch === ':') {
                cell.textContent = ':';
                return;
            }
            flipDigit(cell, ch);
        });
    };

    window.setTimeout(() => {
        tick();
        window.setInterval(tick, 1000);
    }, 1000 - (Date.now() % 1000));
}

function initScope() {
    const scope = document.querySelector('.scope');
    const beam = document.querySelector('.scope__beam');
    const blips = [...document.querySelectorAll('.scope__blip')];
    if (!scope || !beam) return;

    if (reduceMotion) {
        scope.style.setProperty('--sweep', '42deg');
        beam.style.setProperty('--sweep', '42deg');
        blips.forEach((b) => { b.style.opacity = '0.7'; });
        return;
    }

    const period = 4200;
    const start = performance.now();

    function frame(now) {
        const deg = ((now - start) / period) * 360;
        const sweep = deg % 360;
        const value = `${sweep}deg`;
        scope.style.setProperty('--sweep', value);
        beam.style.setProperty('--sweep', value);
        for (const blip of blips) {
            const a = parseFloat(getComputedStyle(blip).getPropertyValue('--a')) || 0;
            const d = Math.abs(((sweep - a + 540) % 360) - 180);
            const hit = d < 16 ? 1 : Math.max(0.16, 1 - (d - 16) / 150);
            blip.style.opacity = String(hit);
        }
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
}

clearRunning();
playVisible();
initClock();
initScope();
watchResults();
