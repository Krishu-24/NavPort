/** Chart.js wind + visibility plots. Muted palette, minimal chrome. */

import { $, cssVar } from '../core/dom.js';
import { clockOnly, visibility } from '../core/format.js';

/** Palette is re-read on every render so a theme switch repaints correctly. */
let INK_3, INK_4, GRID, ACCENT, SURFACE, LINE, OK, WARN, CRIT;

function readPalette() {
    INK_3 = cssVar('--ink-3');
    INK_4 = cssVar('--ink-4');
    GRID = cssVar('--line-soft');
    ACCENT = cssVar('--accent');
    SURFACE = cssVar('--surface');
    LINE = cssVar('--line');
    OK = cssVar('--ok');
    WARN = cssVar('--warn');
    CRIT = cssVar('--crit');
}

let windChart = null;
let visChart = null;

function applyDefaults() {
    const C = window.Chart;
    C.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
    C.defaults.font.size = 11;
    C.defaults.color = INK_3;
    C.defaults.animation.duration = 600;
    C.defaults.animation.easing = 'easeOutQuart';
}

const scales = (extraY = {}) => ({
    y: {
        beginAtZero: true,
        border: { display: false },
        grid: { color: GRID, drawTicks: false },
        ticks: { padding: 10, maxTicksLimit: 4, color: INK_4 },
        ...extraY,
    },
    x: {
        border: { color: GRID },
        grid: { display: false },
        ticks: {
            padding: 8, maxRotation: 0, autoSkipPadding: 24, color: INK_4,
            callback(v) { return clockOnly(this.getLabelForValue(v)); },
        },
    },
});

const tooltip = (extra = {}) => ({
    backgroundColor: SURFACE,
    borderColor: LINE,
    borderWidth: 1,
    titleColor: cssVar('--ink'),
    bodyColor: cssVar('--ink-2'),
    padding: 10,
    cornerRadius: 6,
    displayColors: false,
    titleFont: { size: 11.5, weight: '600' },
    bodyFont: { size: 12 },
    ...extra,
});

export function renderCharts(data) {
    const C = window.Chart;
    if (!C) return;
    readPalette();
    applyDefaults();

    const timeline = data.timeline || [];
    const labels = timeline.map((i) => i.start_time_local);
    const wind = timeline.map((i) => Number(i.wind_speed) || 0);
    const gusts = timeline.map((i) => Number(i.wind_gust) || 0);
    const vis = timeline.map((i) => Math.min(10, Number(i.visibility) || 0));

    windChart?.destroy();
    windChart = new C($('#wind-chart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Sustained',
                    data: wind,
                    borderColor: ACCENT,
                    borderWidth: 1.75,
                    tension: .35,
                    pointRadius: 0,
                    pointHoverRadius: 3.5,
                    pointHoverBackgroundColor: ACCENT,
                    pointHoverBorderColor: SURFACE,
                    fill: true,
                    backgroundColor: (c) => {
                        const { ctx, chartArea } = c.chart;
                        if (!chartArea) return 'transparent';
                        const g = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        g.addColorStop(0, `${ACCENT}24`);
                        g.addColorStop(1, `${ACCENT}00`);
                        return g;
                    },
                },
                {
                    label: 'Gusts',
                    data: gusts,
                    borderColor: INK_4,
                    borderWidth: 1.25,
                    borderDash: [3, 3],
                    tension: .35,
                    pointRadius: 0,
                    pointHoverRadius: 3.5,
                    fill: false,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: scales(),
            plugins: {
                legend: {
                    position: 'top',
                    align: 'end',
                    labels: {
                        boxWidth: 7, boxHeight: 7, usePointStyle: true, pointStyle: 'circle',
                        padding: 14, color: INK_3, font: { size: 11 },
                    },
                },
                tooltip: tooltip({
                    displayColors: true,
                    callbacks: {
                        title: (items) => `${clockOnly(items[0].label)} UTC`,
                        label: (c) => `  ${c.dataset.label} ${Math.round(c.raw)} kt`,
                    },
                }),
            },
        },
    });

    const visColor = (v) => (v < 1 ? CRIT : v < 3 ? WARN : OK);

    visChart?.destroy();
    visChart = new C($('#vis-chart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data: vis,
                backgroundColor: vis.map((v) => `${visColor(v)}D9`),
                hoverBackgroundColor: vis.map(visColor),
                borderRadius: 2,
                borderSkipped: false,
                barPercentage: .72,
                categoryPercentage: .9,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: scales({
                max: 10,
                ticks: { padding: 10, maxTicksLimit: 4, color: INK_4, callback: (v) => (v >= 10 ? '10+' : v) },
            }),
            plugins: {
                legend: { display: false },
                tooltip: tooltip({
                    callbacks: {
                        title: (items) => `${clockOnly(items[0].label)} UTC`,
                        label: (c) => {
                            const raw = Number(c.raw);
                            const band = raw < 1 ? 'Severe' : raw < 3 ? 'Significant' : 'Clear';
                            return `${visibility(raw)} SM · ${band}`;
                        },
                    },
                }),
            },
        },
    });
}

export function destroyCharts() {
    windChart?.destroy();
    visChart?.destroy();
    windChart = visChart = null;
}
