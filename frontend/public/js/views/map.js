/** Leaflet route map: severity-graded path, interval nodes, airport markers. */

import { $, cssVar, esc } from '../core/dom.js';
import { clockOnly, condition, place, sev, visibility } from '../core/format.js';

// Esri canvas basemaps — keyless, and neutral enough to let the route carry colour.
const BASE = (shade) =>
    `https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${shade}_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const REF = (shade) =>
    `https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${shade}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`;
const ATTR = 'Tiles &copy; Esri &middot; Weather &copy; NOAA/AWC';

let map = null;
let layer = null;
let tiles = null;
let labels = null;
let tileShade = null;

function paintTiles(L) {
    const shade = document.documentElement.dataset.theme === 'dark' ? 'Dark' : 'Light';
    if (shade === tileShade) return;
    tileShade = shade;

    tiles?.remove();
    labels?.remove();
    tiles = L.tileLayer(BASE(shade), { attribution: ATTR, maxZoom: 12 }).addTo(map);
    labels = L.tileLayer(REF(shade), { maxZoom: 12, opacity: .9 }).addTo(map);
}

/** Swap basemap shade when the theme changes, without refetching weather. */
export function retintMap() {
    if (map && window.L) paintTiles(window.L);
}

/** "KJFK -> KORD" => ['KJFK', 'KORD'] */
const legCodes = (label = '') => label.split('->').map((s) => s.trim());

function airportIcon(L, code, isEnd) {
    return L.divIcon({
        className: '',
        iconSize: [22, 22],
        iconAnchor: [11, 11],
        html: `<span class="wp-marker${isEnd ? ' wp-marker--end' : ''}" title="${esc(code)}"><span></span></span>`,
    });
}

function popupHtml(item) {
    const s = sev(item.severity);
    return `
        <div class="map-pop__code">${esc(clockOnly(item.start_time_local))} · ${esc(s.label)}</div>
        <div class="map-pop__meta">${esc(place(item.location_description || ''))}</div>
        <div class="map-pop__meta">${esc(condition(item.conditions?.condition || ''))}</div>
        <div class="map-pop__meta">Wind ${Math.round(Number(item.wind_speed) || 0)} kt ·
            Vis ${esc(visibility(item.visibility))} SM</div>`;
}

export function renderMap(data) {
    const host = $('#map');
    const L = window.L;

    const points = (data.timeline || []).filter((i) => Number.isFinite(i.lat) && Number.isFinite(i.lon));

    if (!L || points.length < 2) {
        host.classList.add('map--fallback');
        host.textContent = L ? 'No positional data for this route.' : 'Map unavailable — offline.';
        return;
    }

    host.classList.remove('map--fallback');

    if (!map) {
        map = L.map(host, { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
        map.on('click', () => map.scrollWheelZoom.enable());
        map.on('mouseout', () => map.scrollWheelZoom.disable());
    }

    paintTiles(L);

    layer?.remove();
    layer = L.layerGroup().addTo(map);

    const latlngs = points.map((p) => [p.lat, p.lon]);

    // Casing so the route stays legible over map labels, in either theme
    const casing = cssVar('--surface');
    L.polyline(latlngs, { color: casing, weight: 6, opacity: .9, lineCap: 'round' }).addTo(layer);

    // Severity-graded segments
    for (let i = 0; i < points.length - 1; i++) {
        const worst = ['Severe', 'Significant', 'Clear']
            .find((name) => points[i].severity === name || points[i + 1].severity === name) || 'Clear';

        L.polyline([latlngs[i], latlngs[i + 1]], {
            color: sev(worst).color,
            weight: 2.75,
            opacity: 1,
            lineCap: 'round',
        }).addTo(layer);
    }

    // Interval nodes
    points.forEach((p) => {
        L.circleMarker([p.lat, p.lon], {
            radius: 3,
            color: casing,
            weight: 1.5,
            fillColor: sev(p.severity).color,
            fillOpacity: 1,
        }).bindPopup(popupHtml(p)).addTo(layer);
    });

    // Airport / waypoint markers at leg boundaries
    const stops = [];
    points.forEach((p, i) => {
        const [from, to] = legCodes(p.flight_segment);
        if (i === 0) stops.push({ code: from, ll: latlngs[i] });
        else if (p.flight_segment !== points[i - 1].flight_segment) stops.push({ code: from, ll: latlngs[i] });
        if (i === points.length - 1) stops.push({ code: to, ll: latlngs[i], end: true });
    });

    stops.forEach(({ code, ll, end }) => {
        if (!code) return;
        L.marker(ll, { icon: airportIcon(L, code, end), keyboard: false })
            .bindPopup(`<div class="map-pop__code">${esc(code)}</div>`)
            .addTo(layer);
    });

    map.fitBounds(L.latLngBounds(latlngs).pad(.18), { animate: false });

    // The container was hidden while rendering — force a re-measure.
    requestAnimationFrame(() => map.invalidateSize());
    setTimeout(() => map.invalidateSize(), 220);
}
