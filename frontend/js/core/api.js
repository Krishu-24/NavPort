/** Thin fetch layer over the Flask API. Unchanged endpoints. */

async function request(url, options) {
    const res = await fetch(url, options);
    let body = null;

    try {
        body = await res.json();
    } catch {
        if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
        throw new Error('Malformed response from server');
    }

    if (!res.ok) throw new Error(body?.error || `HTTP ${res.status} ${res.statusText}`);
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
    });
}

export function fetchPireps(station, { raw = false, distance = 150, age = 6 } = {}) {
    const q = new URLSearchParams({ raw: String(raw), distance: String(distance), age: String(age) });
    return request(`/api/pirep-reports/${encodeURIComponent(station)}?${q}`);
}
