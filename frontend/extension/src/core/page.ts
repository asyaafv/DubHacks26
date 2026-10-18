const CHECKOUT_INDICATORS = ['/cart', '/checkout', '/bag', '/basket', 'add-to-cart', 'add_to_cart'];

export interface DetectedPage {
  domain: string;
  isCheckout: boolean;
  url: string;
  title: string;
}

export function normalizeDomain(hostnameOrUrl: string): string {
  const raw = hostnameOrUrl.trim();
  if (!raw) return '';
  try {
    const withProtocol = raw.includes('://') ? raw : `https://${raw}`;
    return new URL(withProtocol).hostname.replace(/^www\./i, '').toLowerCase();
  } catch {
    return raw.replace(/^www\./i, '').split('/')[0]?.toLowerCase() ?? '';
  }
}

export function isCheckoutUrl(url: string): boolean {
  const haystack = url.toLowerCase();
  return CHECKOUT_INDICATORS.some((indicator) => haystack.includes(indicator));
}

/** Returns null for non-http(s) pages such as chrome:// and the extension popup. */
export function detectFromUrl(url: string, title = ''): DetectedPage | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
  return {
    domain: parsed.hostname.replace(/^www\./i, '').toLowerCase(),
    isCheckout: isCheckoutUrl(url),
    url,
    title,
  };
}
