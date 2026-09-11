/**
 * NavPort · dashboard entry point.
 * Loaded as an ES module — every unit below is an explicit import, no globals.
 */

import { $ } from './core/dom.js';
import { defaultDeparture } from './core/format.js';
import { analyzeRoute } from './core/api.js';
import { getState, setState } from './core/state.js';

import { initRail, setBusy, setView, startClock } from './ui/shell.js';
import { initTheme } from './ui/theme.js';
import { toast } from './ui/toast.js';

import { renderOverview } from './views/overview.js';
import { renderBriefing, renderRisk } from './views/risk.js';
import { initRibbonLink, renderRibbon } from './views/ribbon.js';
import { renderCharts } from './views/charts.js';
import { renderMap, retintMap } from './views/map.js';
import { renderNotams } from './views/notams.js';
import { initTimeline, renderTimeline } from './views/timeline.js';
import { initPirepModal } from './views/pireps.js';

/** Read the flight-plan form into a plain object. */
function readPlan() {
    return {
        departure: $('#departure').value.trim().toUpperCase(),
        destination: $('#destination').value.trim().toUpperCase(),
        waypoints: $('#waypoints').value.split(',').map((w) => w.trim().toUpperCase()).filter(Boolean),
        cruiseSpeed: parseInt($('#cruise-speed').value, 10) || 450,
        departureTime: $('#departure-time').value,
    };
}

/** Paint every view from one payload. Order matters only for the map re-measure. */
function renderAll(data) {
    renderOverview(data);
    renderRisk(data);
    renderBriefing(data);
    renderRibbon(data);
    renderNotams(data);
    renderTimeline(data);

    setView('results');       // map + charts need a laid-out container
    renderCharts(data);
    renderMap(data);
}

async function analyze(event) {
    event?.preventDefault();
    if (getState().loading) return;

    const plan = readPlan();

    if (!plan.departure || !plan.destination) {
        toast('Enter both a departure and destination airport.', 'err');
        return;
    }

    if (!plan.departureTime) {
        toast('Pick a departure date and time.', 'err');
        return;
    }

    setState({ loading: true });
    setBusy(true);
    setView('loading');

    try {
        const data = await analyzeRoute(plan);
        setState({ briefing: data, loading: false });
        renderAll(data);

        const severe = data.risk_assessment?.severe_segments || 0;
        toast(
            severe
                ? `Briefing ready · ${severe} severe interval${severe === 1 ? '' : 's'} on route`
                : `Briefing ready · ${data.timeline?.length || 0} intervals analyzed`,
            severe ? 'err' : 'ok',
        );
    } catch (err) {
        console.error(err);
        setState({ loading: false });
        setView(getState().briefing ? 'results' : 'empty');
        toast(err.message || 'Analysis failed.', 'err', 8000);
    } finally {
        setBusy(false);
    }
}

function boot() {
    $('#departure-time').value = defaultDeparture();

    initTheme();
    startClock();
    initRail();
    initTimeline();
    initRibbonLink();
    initPirepModal();

    $('#plan-form').addEventListener('submit', analyze);

    // Canvas and map tiles can't inherit CSS variables — repaint them by hand.
    window.addEventListener('themechange', () => {
        const { briefing } = getState();
        if (!briefing) return;
        renderCharts(briefing);
        retintMap();
    });

    // ICAO fields are uppercase-only by convention
    ['#departure', '#destination', '#waypoints'].forEach((sel) => {
        $(sel).addEventListener('input', (e) => {
            const { selectionStart, selectionEnd } = e.target;
            e.target.value = e.target.value.toUpperCase();
            e.target.setSelectionRange(selectionStart, selectionEnd);
        });
    });

    setView('empty');
}

boot();
