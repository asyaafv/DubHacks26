import { API_BASE, DEMO_USER_ID, USE_MOCKS } from './config';
import { mockLookup, mockRewardAddedEvent, mockStack, mockSync } from './mock';
import type { Event } from '../types';
import type {
  LookupRequest,
  LookupResult,
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

export async function lookup(request: Omit<LookupRequest, 'user_id'>): Promise<LookupResult> {
  const payload: LookupRequest = { ...request, user_id: DEMO_USER_ID, limit: request.limit ?? 3 };
  if (USE_MOCKS) return mockLookup(payload);
  const response = await fetch(`${API_BASE}/lookup`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<LookupResult>;
}

export async function stack(request: Omit<StackRequest, 'user_id'>): Promise<StackResult> {
  const payload: StackRequest = { ...request, user_id: DEMO_USER_ID, items: request.items ?? [] };
  if (USE_MOCKS) return mockStack(payload);
  const response = await fetch(`${API_BASE}/stack`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<StackResult>;
}

export async function sync(since?: string): Promise<SyncResponse> {
  if (USE_MOCKS) return mockSync(since);
  const params = since ? `?since=${encodeURIComponent(since)}` : '';
  const response = await fetch(`${API_BASE}/sync${params}`, { headers: headers() });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<SyncResponse>;
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
