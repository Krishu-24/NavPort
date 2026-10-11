/**
 * NavPort · dashboard entry point.
 * Loaded as an ES module — every unit below is an explicit import, no globals.
 */

import { $, show } from './core/dom.js';
import { defaultDeparture, flightTime } from './core/format.js';
import { analyzeRoute } from './core/api.js';
import { getState, setState } from './core/state.js';

import { initRail, setBusy, setView, startClock } from './ui/shell.js';
import { initTheme } from './ui/theme.js';
import { initRecent, remember } from './ui/recent.js';
import { toast } from './ui/toast.js';
import { initConnection } from './ui/offline.js';

import { renderOverview } from './views/overview.js';
import { renderBriefing, renderRisk } from './views/risk.js';
import { initRibbonLink, renderRibbon } from './views/ribbon.js';
import { renderCharts } from './views/charts.js';
import { renderMap, retintMap } from './views/map.js';
import { renderAlternates, resetAlternates } from './views/alternates.js';
import { renderAirfields } from './views/airfields.js';
import { loadIdentities } from './core/idents.js';
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
    // Identities first — every view below renders codes through them.
    loadIdentities(data.airports);

    renderOverview(data);
    renderRisk(data);
    renderBriefing(data);
    renderRibbon(data);
    renderNotams(data);
    renderAirfields(data);
    renderTimeline(data);

    renderPrintHeader(data);

    setView('results');       // map + charts need a laid-out container
    renderCharts(data);
    renderMap(data);
    renderAlternates(data);   // fires its own request, paints when it lands
    show($('#print-btn'), true);
}

/** Only visible on paper — identifies the briefing and when it was pulled. */
function renderPrintHeader(data) {
    const r = data.route || {};
    const via = r.waypoints?.length ? ` via ${r.waypoints.join(' ')}` : '';
    $('#print-route').textContent = `${r.departure} → ${r.destination}${via}`;

    $('#print-meta').textContent = [
        `${Math.round(r.total_distance)} nm`,
        flightTime(r.total_flight_time),
        `${r.cruise_speed} kts`,
        `Worst on route: ${r.flight_category}`,
        `Generated ${new Date().toUTCString()}`,
    ].join('  ·  ');
}

/** Set by boot(); lets analyze() dismiss the off-canvas rail on phones. */
let rail = null;

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
    // On a phone the form covers the whole screen, so leaving it open hides
    // the very result it just asked for. Closing here rather than on click
    // means a rejected plan keeps the form up, with the offending field in
    // view. On desktop the rail is not off-canvas and this is a no-op.
    rail?.close();
    setView('loading');
    resetAlternates();

    try {
        const data = await analyzeRoute(plan);
        setState({ briefing: data, loading: false });
        renderAll(data);
        remember(plan);

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

        // Being throttled is recoverable and the server says when to retry, so
        // that is more useful to show than the generic message.
        const message = err.retryAfter
            ? `Too many briefings — try again in ${err.retryAfter}s.`
            : err.message || 'Analysis failed.';

        toast(message, 'err', err.offline ? 10000 : 8000);
    } finally {
        setBusy(false);
    }
}

function boot() {
    $('#departure-time').value = defaultDeparture();

    initTheme();
    initConnection();
    startClock();
    rail = initRail();
    initTimeline();
    initRibbonLink();
    initPirepModal();

    $('#plan-form').addEventListener('submit', analyze);
    $('#print-btn').addEventListener('click', () => window.print());

    initRecent((route) => {
        $('#departure').value = route.departure;
        $('#destination').value = route.destination;
        $('#waypoints').value = (route.waypoints || []).join(', ');
        if (route.cruiseSpeed) $('#cruise-speed').value = route.cruiseSpeed;
        analyze();
    });

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
