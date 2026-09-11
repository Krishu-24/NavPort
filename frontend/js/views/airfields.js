/** Departure and destination field conditions, including density altitude —
 *  a standard element of an FAA preflight briefing and the number that decides
 *  whether the aircraft will actually perform today. */

import { $, el, show } from '../core/dom.js';
import { cat, visibility } from '../core/format.js';
import { ident } from '../core/idents.js';

function readout(label, value, tone = '') {
    return el('div', { class: 'field-readout' },
        el('div', { class: 'field-readout__label' }, label),
        el('div', { class: `field-readout__value${tone ? ` field-readout__value--${tone}` : ''}` }, value),
    );
}

function windText(report) {
    const speed = Math.round(report.wind_speed || 0);
    if (!speed) return 'Calm';
    const gust = report.wind_gust ? `G${Math.round(report.wind_gust)}` : '';
    const dir = report.wind_dir === null || report.wind_dir === undefined
        ? '' : `${String(report.wind_dir).padStart(3, '0')}° `;
    return `${dir}${speed}${gust} kt`;
}

function card(role, code, report) {
    const c = cat(report.flight_category);
    const perf = report.performance;

    return el('article', { class: 'airfield' },
        el('div', { class: 'airfield__head' },
            el('span', { class: 'airfield__role' }, role),
            ident(code, { className: 'airfield__code' }),
            report.flight_category
                ? el('span', { class: `cat cat--${c.key}`, title: c.title }, c.label)
                : null,
        ),

        report.observed
            ? el('div', { class: 'airfield__grid' },
                readout('Wind', windText(report)),
                readout('Visibility', report.visibility_sm === null || report.visibility_sm === undefined
                    ? '—' : `${visibility(report.visibility_sm)} sm`),
                readout('Temp', report.temp_c === null || report.temp_c === undefined
                    ? '—' : `${Math.round(report.temp_c)}°C`),
                readout('Altimeter', report.altimeter_hpa
                    ? `${(report.altimeter_hpa / 33.8639).toFixed(2)} inHg` : '—'),
            )
            : el('p', { class: 'airfield__none' }, 'No current observation for this field.'),

        perf
            ? el('div', { class: `airfield__perf${perf.significant ? ' is-significant' : ''}` },
                el('div', { class: 'airfield__perf-main' },
                    el('span', { class: 'airfield__perf-label' }, 'Density altitude'),
                    el('span', { class: 'airfield__perf-value' },
                        `${perf.density_altitude_ft.toLocaleString()} ft`),
                ),
                el('div', { class: 'airfield__perf-sub' },
                    `Field ${perf.field_elevation_ft.toLocaleString()} ft · `,
                    `Pressure alt ${perf.pressure_altitude_ft.toLocaleString()} ft · `,
                    `ISA ${perf.isa_deviation_c > 0 ? '+' : ''}${perf.isa_deviation_c}°C`,
                ),
                perf.significant
                    ? el('p', { class: 'airfield__warn' },
                        `${(perf.density_altitude_ft - perf.field_elevation_ft).toLocaleString()} ft above field elevation — check takeoff and climb performance.`)
                    : null,
            )
            : null,
    );
}

export function renderAirfields(data) {
    const section = $('#airfields-section');
    const fields = data.airfields || {};
    const codes = [data.route?.departure, data.route?.destination].filter(Boolean);

    if (!codes.length || !Object.keys(fields).length) return show(section, false);

    $('#airfields-body').replaceChildren(
        ...codes.map((code, i) => {
            const report = fields[code];
            return report ? card(i === 0 ? 'Departure' : 'Destination', code, report) : null;
        }).filter(Boolean),
    );

    const worst = codes
        .map((c) => fields[c]?.performance)
        .filter(Boolean)
        .some((p) => p.significant);

    $('#airfields-tag').textContent = worst
        ? 'high density altitude — check performance'
        : 'field conditions at both ends';

    show(section, true);
}
