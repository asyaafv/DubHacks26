import type { EventType, LookupResult } from '../types';

export interface ToastRecord {
  id: string;
  message: string;
  event_type: EventType;
  reward_id?: string | null;
}

export interface StoredState {
  currentLookup: LookupResult | null;
  currentDomain: string;
  currentUrl: string;
  isCheckout: boolean;
  pageTitle: string;
  toasts: ToastRecord[];
  lastError: string | null;
}

export interface PageVisitMessage {
  type: 'PAGE_VISIT';
  domain: string;
  isCheckout: boolean;
  url: string;
  title: string;
}

export interface CalculateStackMessage {
  type: 'CALCULATE_STACK';
  domain: string;
  cartTotal: string;
}

export interface GetStateMessage {
  type: 'GET_STATE';
}

export interface DismissToastMessage {
  type: 'DISMISS_TOAST';
  id: string;
}

export type ExtensionMessage =
  | PageVisitMessage
  | CalculateStackMessage
  | GetStateMessage
  | DismissToastMessage;

export type RpcResult<T> = { ok: true; data: T } | { ok: false; error: string };

export function emptyState(): StoredState {
  return {
    currentLookup: null,
    currentDomain: '',
    currentUrl: '',
    isCheckout: false,
    pageTitle: '',
    toasts: [],
    lastError: null,
  };
}
