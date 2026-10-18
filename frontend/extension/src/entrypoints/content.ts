import { detectFromUrl } from '../core/page';
import { daysUntilExpiry, formatExpiry, formatRewardValue } from '../core/format';
import { expiryFraction, urgencyFromDays, URGENCY_COLORS, RING_TRACK_COLOR } from '../components/ExpiryRing';
import type { RpcResult } from '../core/messages';
import type { LookupResult } from '../types';

const TOAST_LIFETIME_MS = 10_000;

/** Same ring math as the popup's ExpiryRing, rendered as a plain SVG string. */
function ringSvg(fraction: number, color: string, size: number, stroke: number): string {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * Math.min(1, Math.max(0, fraction));
  const center = size / 2;
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg);display:block" aria-hidden="true">` +
    `<circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="${RING_TRACK_COLOR}" stroke-width="${stroke}"></circle>` +
    `<circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-dasharray="${dash} ${circumference}"></circle>` +
    `</svg>`
  );
}

function showLapseSenseToast(lookup: LookupResult, domain: string): void {
  if (!document.body) return;

  const top = lookup.rewards[0];
  if (!top) return;
  const reward = top.reward;
  const merchant = lookup.merchant?.name || reward.merchant_name || domain;
  const days = top.days_until_expiry ?? daysUntilExpiry(reward.expires_at);
  const expiry = formatExpiry(days);
  const bodyText = `${formatRewardValue(reward)} at ${merchant}${expiry ? ` — ${expiry}` : ''}`;

  const host = document.createElement('div');
  host.setAttribute('data-testid', 'lapse-sense-toast');
  // Positioning lives on the host itself (inline, so page styles cannot reflow it).
  host.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483647;width:300px;';

  const shadow = host.attachShadow({ mode: 'closed' });

  const style = document.createElement('style');
  style.textContent = `
    @keyframes lapse-slide-in {
      from { transform: translateX(120%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    .card {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      background: #FFF6E9;
      color: #141414;
      border: 2px solid #141414;
      box-shadow: 5px 5px 0 #141414;
      padding: 10px 12px;
      font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
      animation: lapse-slide-in 0.25s ease-out;
    }
    .ring { flex: none; padding-top: 2px; }
    .text { min-width: 0; flex: 1; }
    .title {
      font-family: Archivo, 'Arial Black', sans-serif;
      font-weight: 900;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .body { margin-top: 2px; font-size: 12px; font-weight: 600; line-height: 1.35; }
    .close {
      flex: none;
      border: 2px solid #141414;
      background: #BCE740;
      color: #141414;
      font-weight: 900;
      font-size: 12px;
      line-height: 1;
      width: 20px;
      height: 20px;
      padding: 0;
      cursor: pointer;
    }
  `;
  shadow.appendChild(style);

  const card = document.createElement('div');
  card.className = 'card';

  const ring = document.createElement('div');
  ring.className = 'ring';
  ring.innerHTML = ringSvg(
    expiryFraction(reward.created_at, reward.expires_at),
    URGENCY_COLORS[urgencyFromDays(days)],
    22,
    4,
  );

  const text = document.createElement('div');
  text.className = 'text';
  const title = document.createElement('div');
  title.className = 'title';
  title.textContent = '✂ LAPSE SENSE';
  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = bodyText;
  text.append(title, body);

  const close = document.createElement('button');
  close.className = 'close';
  close.type = 'button';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '×';

  card.append(ring, text, close);
  shadow.appendChild(card);
  document.body.appendChild(host);

  const timer = window.setTimeout(() => host.remove(), TOAST_LIFETIME_MS);
  close.addEventListener('click', () => {
    window.clearTimeout(timer);
    host.remove();
  });
}

export default defineContentScript({
  matches: ['*://*/*'],
  runAt: 'document_idle',
  main(ctx) {
    let lastKey = '';
    // One Lapse Sense toast per domain per page load.
    const sensedDomains = new Set<string>();

    const report = () => {
      const page = detectFromUrl(window.location.href, document.title);
      if (!page) return;
      const key = `${page.domain}|${page.isCheckout}|${page.url}`;
      if (key === lastKey) return;
      lastKey = key;
      void browser.runtime
        .sendMessage({ type: 'PAGE_VISIT', ...page })
        .then((response) => {
          // PAGE_VISIT already answers with the lookup for this domain; reuse it.
          const result = response as RpcResult<LookupResult> | undefined;
          if (!result?.ok || sensedDomains.has(page.domain)) return;
          if (result.data.rewards.length < 1) return;
          sensedDomains.add(page.domain);
          showLapseSenseToast(result.data, page.domain);
        })
        .catch(() => {
          // The service worker may be restarting. The next navigation or popup open retries.
        });
    };

    report();
    ctx.addEventListener(window, 'popstate', report);
    ctx.addEventListener(window, 'hashchange', report);
    ctx.setInterval(report, 1500);
  },
});
