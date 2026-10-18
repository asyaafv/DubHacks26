import { useEffect, useState } from 'react';
import { detectFromUrl } from '../core/page';
import { type RpcResult, type StoredState } from '../core/messages';
import { sendMessage } from '../core/runtime';
import type { LookupResult } from '../types';

export function useRewards() {
  const [lookup, setLookup] = useState<LookupResult | null>(null);
  const [domain, setDomain] = useState('');
  const [isCheckout, setIsCheckout] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (typeof browser === 'undefined' || !browser.runtime?.id) {
      setError('Open Lapse from the Chrome toolbar.');
      setLoading(false);
      return;
    }

    async function load() {
      const stored = await sendMessage<RpcResult<StoredState>>({ type: 'GET_STATE' });
      if (cancelled) return;
      if (stored.ok) {
        setLookup(stored.data.currentLookup);
        setDomain(stored.data.currentDomain);
        setIsCheckout(stored.data.isCheckout);
        if (stored.data.lastError) setError(stored.data.lastError);
      }

      const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
      const detected = tab?.url ? detectFromUrl(tab.url, tab.title ?? '') : null;
      if (!detected) {
        setLoading(false);
        return;
      }

      setDomain(detected.domain);
      setIsCheckout(detected.isCheckout);
      const response = await sendMessage<RpcResult<LookupResult>>({
        type: 'PAGE_VISIT',
        domain: detected.domain,
        isCheckout: detected.isCheckout,
        url: detected.url,
        title: detected.title,
      });
      if (cancelled) return;
      if (response.ok) {
        setLookup(response.data);
        setError(null);
      } else {
        setError(response.error);
      }
      setLoading(false);
    }

    void load().catch((err: unknown) => {
      if (cancelled) return;
      setError(err instanceof Error ? err.message : 'Could not load rewards.');
      setLoading(false);
    });

    const onChanged: Parameters<typeof browser.storage.onChanged.addListener>[0] = (changes, area) => {
      if (area !== 'local' || cancelled) return;
      if (changes.currentLookup) setLookup((changes.currentLookup.newValue as LookupResult | null) ?? null);
      if (changes.currentDomain) setDomain((changes.currentDomain.newValue as string) ?? '');
      if (changes.isCheckout) setIsCheckout(Boolean(changes.isCheckout.newValue));
      if (changes.lastError) setError((changes.lastError.newValue as string | null) ?? null);
    };
    browser.storage.onChanged.addListener(onChanged);

    return () => {
      cancelled = true;
      browser.storage.onChanged.removeListener(onChanged);
    };
  }, []);

  return { lookup, domain, isCheckout, loading, error };
}
