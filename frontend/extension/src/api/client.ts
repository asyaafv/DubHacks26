import { API_BASE, DEMO_USER_ID, USE_MOCKS } from './config';
import { mockLookup, mockRedeem, mockRewardAddedEvent, mockStack, mockSync } from './mock';
import type { Event } from '../types';
import type {
  LookupRequest,
  LookupResult,
  Reward,
  StackRequest,
  StackResult,
  SyncResponse,
} from '../types';

function headers(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-User-Id': DEMO_USER_ID,
  };
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string };
    if (body?.message) return body.message;
  } catch {
    // The body was not the contract error shape.
  }
  return `Request failed (${response.status})`;
}

/**
 * True only for network-level failures (server down, DNS, no host permission).
 * HTTP errors (4xx/5xx) are real backend answers and must surface, not be mocked.
 */
function isUnreachable(error: unknown): boolean {
  return error instanceof TypeError;
}

/** Live call with an automatic, clearly logged mock fallback when the backend is unreachable. */
async function liveOrMock<T>(label: string, live: () => Promise<T>, mock: () => T): Promise<T> {
  if (USE_MOCKS) return mock();
  try {
    return await live();
  } catch (error) {
    if (!isUnreachable(error)) throw error;
    console.warn(`[Lapse] backend unreachable at ${API_BASE} — serving MOCK ${label}`, error);
    return mock();
  }
}

export async function lookup(request: Omit<LookupRequest, 'user_id'>): Promise<LookupResult> {
  const limit = request.limit ?? 3;
  const payload: LookupRequest = { ...request, user_id: DEMO_USER_ID, limit };
  return liveOrMock(
    'lookup',
    async () => {
      // The backend ranks across ALL merchants (category matches score 0.7),
      // so ask for the deepest allowed page (le=10) and keep only codes usable
      // at THIS merchant (match_component === 1), mirroring the mock's behavior.
      const response = await fetch(`${API_BASE}/lookup`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ ...payload, limit: 10 }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const result = (await response.json()) as LookupResult;
      const exact = result.rewards.filter((scored) => scored.match_component === 1);
      return { ...result, rewards: exact.slice(0, limit) };
    },
    () => mockLookup(payload),
  );
}

export async function stack(request: Omit<StackRequest, 'user_id'>): Promise<StackResult> {
  const payload: StackRequest = { ...request, user_id: DEMO_USER_ID, items: request.items ?? [] };
  return liveOrMock(
    'stack',
    async () => {
      const response = await fetch(`${API_BASE}/stack`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await readError(response));
      return response.json() as Promise<StackResult>;
    },
    () => mockStack(payload),
  );
}

export async function sync(since?: string): Promise<SyncResponse> {
  const params = since ? `?since=${encodeURIComponent(since)}` : '';
  return liveOrMock(
    'sync',
    async () => {
      const response = await fetch(`${API_BASE}/sync${params}`, { headers: headers() });
      if (!response.ok) throw new Error(await readError(response));
      return response.json() as Promise<SyncResponse>;
    },
    () => mockSync(since),
  );
}

/** POST /rewards/{id}/redeem — marks the reward used and records the redemption. */
export async function redeemReward(rewardId: string, saved?: string): Promise<Reward> {
  return liveOrMock(
    'redeem',
    async () => {
      const response = await fetch(`${API_BASE}/rewards/${rewardId}/redeem`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(saved ? { saved } : {}),
      });
      if (!response.ok) throw new Error(await readError(response));
      return response.json() as Promise<Reward>;
    },
    () => mockRedeem(rewardId),
  );
}

/**
 * Live mode reads `GET /events` with fetch so the service worker can send `X-User-Id`.
 * Mock mode emits one seed `reward_added` and does not touch the network.
 * Callers should catch and fall back to `sync`.
 */
export async function* listenForEvents(signal?: AbortSignal): AsyncGenerator<Event> {
  if (USE_MOCKS) {
    yield mockRewardAddedEvent();
    return;
  }

  const response = await fetch(`${API_BASE}/events`, {
    headers: {
      Accept: 'text/event-stream',
      'X-User-Id': DEMO_USER_ID,
    },
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(response.ok ? 'Event stream had no body' : await readError(response));
  }

  const { feedSseBuffer } = await import('../core/sse');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = feedSseBuffer(buffer);
    buffer = parsed.rest;
    for (const frame of parsed.frames) {
      yield JSON.parse(frame.data) as Event;
    }
  }
}
