/** Tiny observable store — the single source of truth for the dashboard. */

const state = {
    briefing: null,   // last successful /api/enhanced-flight-plan payload
    loading: false,
    activeInterval: null,
};

const listeners = new Set();

export const getState = () => state;

export function setState(patch) {
    Object.assign(state, patch);
    listeners.forEach((fn) => fn(state));
}

export function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
}
