/** Demo user from the shared contract. The extension always acts as this user. */
export const DEMO_USER_ID = '00000000-0000-0000-0000-000000000001';
export const DEMO_USER_EMAIL = 'aamir@lapse.app';

const env = import.meta.env ?? {};

function envValue(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}

/** API origin. `VITE_API_BASE` overrides the localhost default at build time. */
export const API_BASE = envValue(env.VITE_API_BASE, 'http://localhost:8000').replace(/\/$/, '');

/**
 * Mock switch. Live API calls are the default; set `VITE_USE_MOCKS=true` to force
 * `shared/seed` data with no backend. In live mode the client still falls back to
 * mocks automatically (with a console warning) when the backend is unreachable.
 */
export const USE_MOCKS = env.VITE_USE_MOCKS === 'true';

/** Web app dashboard. Not part of the API contract; override with `VITE_DASHBOARD_URL`. */
export const DASHBOARD_URL = envValue(env.VITE_DASHBOARD_URL, 'http://localhost:5173/dashboard');
