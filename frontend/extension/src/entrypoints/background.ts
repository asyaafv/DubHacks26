import { lookup, listenForEvents, stack, sync } from '../api/client';
import { USE_MOCKS } from '../api/config';
import { toastMessage } from '../api/mock';
import {
  emptyState,
  type CalculateStackMessage,
  type DismissToastMessage,
  type PageVisitMessage,
  type RpcResult,
  type StoredState,
  type ToastRecord,
} from '../core/messages';
import type { Event } from '../types';

export default defineBackground(() => {
  browser.runtime.onMessage.addListener((message: { type?: string }, sender) => {
    const respond = async (): Promise<RpcResult<unknown>> => {
      switch (message?.type) {
        case 'PAGE_VISIT':
          return handlePageVisit(message as PageVisitMessage, sender.tab?.id);
        case 'CALCULATE_STACK':
          return handleStack(message as CalculateStackMessage);
        case 'GET_STATE':
          return { ok: true, data: await readState() };
        case 'DISMISS_TOAST':
          return dismissToast(message as DismissToastMessage);
        default:
          return { ok: false, error: 'Unknown message' };
      }
    };

    return respond().catch((error: unknown) => {
      const text = error instanceof Error ? error.message : 'Background error';
      return { ok: false, error: text } satisfies RpcResult<never>;
    });
  });

  void startEvents();
});

async function readState(): Promise<StoredState> {
  const stored = await browser.storage.local.get(Object.keys(emptyState()));
  return { ...emptyState(), ...(stored as Partial<StoredState>) };
}

async function setBadge(count: number, tabId?: number): Promise<void> {
  const text = count > 0 ? String(count) : '';
  await browser.action.setBadgeText({ text });
  await browser.action.setBadgeBackgroundColor({ color: '#174B34' });
  const action = browser.action as typeof browser.action & {
    setBadgeTextColor?: (details: { color: string; tabId?: number }) => Promise<void>;
  };
  if (action.setBadgeTextColor) await action.setBadgeTextColor({ color: '#FFFFFF' });
  if (tabId == null) return;
  await browser.action.setBadgeText({ text, tabId });
  await browser.action.setBadgeBackgroundColor({ color: '#174B34', tabId });
  if (action.setBadgeTextColor) await action.setBadgeTextColor({ color: '#FFFFFF', tabId });
}

async function handlePageVisit(message: PageVisitMessage, tabId?: number): Promise<RpcResult<unknown>> {
  try {
    const result = await lookup({ domain: message.domain, limit: 3 });
    await browser.storage.local.set({
      currentLookup: result,
      currentDomain: message.domain,
      currentUrl: message.url,
      isCheckout: message.isCheckout,
      pageTitle: message.title,
      lastError: null,
    });
    await setBadge(result.rewards.length, tabId);
    return { ok: true, data: result };
  } catch (error) {
    const text = error instanceof Error ? error.message : 'Lookup failed';
    await browser.storage.local.set({
      currentDomain: message.domain,
      currentUrl: message.url,
      isCheckout: message.isCheckout,
      pageTitle: message.title,
      lastError: text,
    });
    await browser.action.setBadgeText({ text: '!', ...(tabId == null ? {} : { tabId }) });
    return { ok: false, error: text };
  }
}

async function handleStack(message: CalculateStackMessage): Promise<RpcResult<unknown>> {
  const result = await stack({
    domain: message.domain,
    cart_total: message.cartTotal,
    items: [],
  });
  return { ok: true, data: result };
}

async function dismissToast(message: DismissToastMessage): Promise<RpcResult<{ toasts: ToastRecord[] }>> {
  const state = await readState();
  const toasts = state.toasts.filter((toast) => toast.id !== message.id);
  await browser.storage.local.set({ toasts });
  return { ok: true, data: { toasts } };
}

async function publishEvent(event: Event): Promise<void> {
  const message = toastMessage(event);
  if (!message) return;
  const id = `${event.event_type}:${event.reward_id ?? ''}:${event.timestamp ?? ''}:${message}`;
  try {
    const stored = await browser.storage.session.get('seenEventIds');
    const seen = ((stored.seenEventIds as string[] | undefined) ?? []);
    if (seen.includes(id)) return;
    await browser.storage.session.set({ seenEventIds: [...seen, id].slice(-50) });
  } catch {
    // Session storage can be unavailable in older runtimes; still show the toast.
  }

  const state = await readState();
  const toasts = [...state.toasts.filter((toast) => toast.id !== id), {
    id,
    message,
    event_type: event.event_type,
    reward_id: event.reward_id,
  }].slice(-3);
  await browser.storage.local.set({ toasts });

  if (state.currentDomain) {
    await handlePageVisit({
      type: 'PAGE_VISIT',
      domain: state.currentDomain,
      isCheckout: state.isCheckout,
      url: state.currentUrl,
      title: state.pageTitle,
    });
  }
}

async function poll(onEvent: (event: Event) => Promise<void>): Promise<void> {
  let since: string | undefined;
  const tick = async () => {
    const payload = await sync(since);
    since = payload.last_sync;
    for (const event of payload.pending_events ?? []) await onEvent(event);
  };
  await tick();
  setInterval(() => {
    void tick().catch((error: unknown) => {
      console.warn('[Lapse] sync poll failed', error);
    });
  }, 15_000);
}

async function startEvents(): Promise<void> {
  console.info(`[Lapse] ${USE_MOCKS ? 'mock' : 'live'} mode`);
  try {
    for await (const event of listenForEvents()) {
      await publishEvent(event);
    }
  } catch (error) {
    console.warn('[Lapse] /events unavailable, polling /sync', error);
    try {
      await poll(publishEvent);
    } catch (pollError) {
      console.warn('[Lapse] sync fallback failed', pollError);
    }
  }
}
