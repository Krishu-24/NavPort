/** Risk gauge + severity breakdown, briefing copy, and the data-source line. */

import { $, el, animateNumber, cssVar, nextFrame } from '../core/dom.js';

const R = 42;                     // gauge radius
const SWEEP = 260;                // degrees of arc
const CIRC = 2 * Math.PI * R;
const ARC = CIRC * (SWEEP / 360);

const TONE = {
    'LOW RISK':      'ok',
    'MODERATE RISK': 'warn',
    'HIGH RISK':     'crit',
};

function tone(level) {
    const key = TONE[level] || 'ink-3';
    return { key: TONE[level] || 'quiet', color: cssVar(`--${key}`) };
}

function gaugeSvg(color, pct) {
    const offset = ARC * (1 - Math.min(100, Math.max(0, pct)) / 100);
    const rotate = 90 + (360 - SWEEP) / 2;

    return `
        <svg viewBox="0 0 96 96" aria-hidden="true">
            <g transform="rotate(${rotate} 48 48)">
                <circle class="gauge__track" cx="48" cy="48" r="${R}" fill="none"
                        stroke-width="5" stroke-linecap="round"
                        stroke-dasharray="${ARC} ${CIRC}"/>
                <circle class="gauge__fill" cx="48" cy="48" r="${R}" fill="none"
                        stroke="${color}" stroke-width="5"
                        stroke-dasharray="${ARC} ${CIRC}"
                        stroke-dashoffset="${ARC}"
                        data-target="${offset}"/>
            </g>
        </svg>`;
}

function bar(label, count, total, color) {
    const pct = total ? (count / total) * 100 : 0;
    return el('li', { class: 'bar' },
        el('span', { class: 'bar__label' }, label),
        el('span', { class: 'bar__track' },
            el('span', { class: 'bar__fill', style: `width:${pct}%;background:${color}` }),
        ),
        el('span', { class: 'bar__n' }, String(count)),
    );
}

export function renderRisk(data) {
    const risk = data.risk_assessment || {};
    const t = tone(risk.risk_level);
    const pct = Number(risk.risk_percentage) || 0;
    const total = risk.total_segments || 0;
    const severe = risk.severe_segments || 0;
    const significant = risk.significant_segments || 0;

    const level = $('#risk-level');
    level.className = `risk__level risk__level--${t.key}`;
    level.textContent = (risk.risk_level || 'Unknown').replace(' RISK', ' risk').replace(/^(\w)(\w*)/, (_, a, b) => a + b.toLowerCase());

    const gauge = $('#gauge');
    gauge.innerHTML = gaugeSvg(t.color, pct);

    const center = el('div', { class: 'gauge__center' },
        el('div', { class: 'gauge__pct' }, '0', el('sup', {}, '%')),
    );
    gauge.append(center);
    animateNumber(center.querySelector('.gauge__pct').firstChild, pct, { decimals: 0 });

    const fill = gauge.querySelector('.gauge__fill');
    nextFrame(() => { fill.style.strokeDashoffset = fill.dataset.target; });

    $('#risk-rec').textContent = risk.recommendation || '—';

    $('#seg-stats').replaceChildren(
        bar('Severe', severe, total, cssVar('--crit')),
        bar('Significant', significant, total, cssVar('--warn')),
        bar('Clear', Math.max(0, total - severe - significant), total, cssVar('--ok')),
    );
}

const SOURCE_LABELS = [
    ['metars_count', 'METAR'],
    ['tafs_count', 'TAF'],
    ['pireps_count', 'PIREP'],
    ['sigmets_count', 'SIGMET'],
    ['gairmets_count', 'G-AIRMET'],
    ['cwas_count', 'CWA'],
    ['notams_count', 'NOTAM'],
];

export function renderBriefing(data) {
    $('#brief-text').textContent = data.nlp_briefing_summary || 'No briefing available for this route.';

    const summary = data.weather_summary || {};
    $('#sources').replaceChildren(
        ...SOURCE_LABELS.map(([key, label]) =>
            el('span', {}, el('b', {}, String(summary[key] ?? 0)), ` ${label}`)),
    );
}
