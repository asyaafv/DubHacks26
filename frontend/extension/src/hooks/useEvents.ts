import { useEffect, useState } from 'react';
import { emptyState, type RpcResult, type StoredState, type ToastRecord } from '../core/messages';
import { sendMessage } from '../core/runtime';

export function useEvents() {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (typeof browser === 'undefined' || !browser.runtime?.id || !browser.storage?.onChanged) {
      return;
    }
    void sendMessage<RpcResult<StoredState>>({ type: 'GET_STATE' })
      .then((response) => {
        if (!cancelled && response.ok) setToasts(response.data.toasts ?? []);
      })
      .catch(() => {
        if (!cancelled) setToasts(emptyState().toasts);
      });

    const onChanged: Parameters<typeof browser.storage.onChanged.addListener>[0] = (changes, area) => {
      if (area !== 'local' || !changes.toasts || cancelled) return;
      setToasts((changes.toasts.newValue as ToastRecord[] | undefined) ?? []);
    };
    browser.storage.onChanged.addListener(onChanged);
    return () => {
      cancelled = true;
      browser.storage.onChanged.removeListener(onChanged);
    };
  }, []);

  function dismiss(id: string) {
    void sendMessage({ type: 'DISMISS_TOAST', id });
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }

  return { toasts, dismiss };
}
