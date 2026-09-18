/** Thin fetch layer over the Flask API. */

import { apiUrl } from '../config.js';

/** A briefing legitimately takes several seconds; the rest should be quick. */
const TIMEOUTS = { default: 20_000, briefing: 120_000 };

/**
 * Thrown for every API failure, carrying enough structure for the UI to react
 * differently to "you're offline", "slow down" and "that route is invalid".
 */
export class ApiError extends Error {
    constructor(message, { status = 0, offline = false, timeout = false, retryAfter = null } = {}) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.offline = offline;
        this.timeout = timeout;
        this.retryAfter = retryAfter;
    }
}

async function request(path, options = {}, timeout = TIMEOUTS.default) {
    // Give up on our own terms. Without this a request on a network that
    // accepts connections but never answers — hotel and airport wifi, captive
    // portals — hangs the spinner indefinitely.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    let res;
    try {
        res = await fetch(apiUrl(path), { ...options, signal: controller.signal });
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new ApiError('The server took too long to respond. Try again.', { timeout: true });
        }
        // fetch() rejects with a TypeError for DNS failure, refused
        // connections and no network — indistinguishable from each other by
        // design, so `navigator.onLine` is the only extra signal available.
        throw new ApiError(
            navigator.onLine
                ? 'Could not reach the NavPort server.'
                : 'You appear to be offline. Weather data needs a connection.',
            { offline: true },
        );
    } finally {
        clearTimeout(timer);
    }

    let body = null;
    try {
        body = await res.json();
    } catch {
        if (!res.ok) throw new ApiError(`HTTP ${res.status} ${res.statusText}`, { status: res.status });
        throw new ApiError('Malformed response from server', { status: res.status });
    }

    if (!res.ok) {
        throw new ApiError(
            body?.error || `HTTP ${res.status} ${res.statusText}`,
            {
                status: res.status,
                retryAfter: body?.retry_after_seconds ?? null,
            },
        );
    }

    return body;
}

export function analyzeRoute(plan) {
    return request('/api/enhanced-flight-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            departure: plan.departure,
            destination: plan.destination,
            waypoints: plan.waypoints,
            cruise_speed: plan.cruiseSpeed,
            departure_time: plan.departureTime,
        }),
    }, TIMEOUTS.briefing);
}

export function fetchAlternates(icao, { radius = 200, limit = 8 } = {}) {
    const q = new URLSearchParams({ radius: String(radius), limit: String(limit) });
    return request(`/api/alternates/${encodeURIComponent(icao)}?${q}`);
}

export function fetchPireps(station, { raw = false, distance = 150, age = 6 } = {}) {
    const q = new URLSearchParams({ raw: String(raw), distance: String(distance), age: String(age) });
    return request(`/api/pirep-reports/${encodeURIComponent(station)}?${q}`);
}

/** Server reachability and whether its airport database loaded. */
export function fetchHealth() {
    return request('/api/health', {}, 5000);
}
