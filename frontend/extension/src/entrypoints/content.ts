import { detectFromUrl } from '../core/page';
import { daysUntilExpiry, formatExpiry, formatMoney, formatRewardValue } from '../core/format';
import { expiryFraction, urgencyFromDays, URGENCY_COLORS, RING_TRACK_COLOR } from '../components/ExpiryRing';
import type { RpcResult } from '../core/messages';
import type { LookupResult, StackResult } from '../types';

const COLLAPSE_AFTER_MS = 12_000;

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

/**
 * Best-effort cart total from the page text (e.g. "Subtotal: $500.00") so the
 * toast can preview the stack. Only consulted on checkout-looking pages.
 */
function detectCartTotal(): string | null {
  const text = document.body?.innerText ?? '';
  const match = text.match(/(?:subtotal|order total|cart total|total)\s*:?\s*\$\s*([\d,]+(?:\.\d{2})?)/i);
  if (!match?.[1]) return null;
  const amount = Number(match[1].replace(/,/g, ''));
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return amount.toFixed(2);
}

const CSS = `
  @keyframes lapse-slide-in {
    from { transform: translateX(120%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  * { box-sizing: border-box; }
  .wrap { font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif; color: #141414; }
  .card {
    width: 380px;
    background: #FFF6E9;
    border: 2px solid #141414;
    box-shadow: 6px 6px 0 #141414;
    animation: lapse-slide-in 0.3s ease-out;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: #FF5C1C;
    border-bottom: 2px solid #141414;
  }
  .brand {
    font-family: Archivo, 'Arial Black', sans-serif;
    font-weight: 900;
    font-size: 13px;
    letter-spacing: 0.08em;
    color: #fff;
    flex: 1;
  }
  .count {
    background: #141414;
    color: #BCE740;
    font-weight: 700;
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 2px 6px;
  }
  .close {
    border: 2px solid #141414;
    background: #BCE740;
    color: #141414;
    font-weight: 900;
    font-size: 13px;
    line-height: 1;
    width: 22px;
    height: 22px;
    padding: 0;
    cursor: pointer;
  }
  .main { display: flex; gap: 12px; padding: 12px; align-items: flex-start; }
  .ringbox { flex: none; text-align: center; }
  .expires { margin-top: 3px; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
  .text { min-width: 0; flex: 1; }
  .merchant { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; }
  .value {
    font-family: Archivo, 'Arial Black', sans-serif;
    font-weight: 900;
    font-size: 26px;
    line-height: 1.05;
    margin-top: 2px;
  }
  .codes {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 12px 10px;
    border: 2px solid #141414;
    background: #fff;
    padding: 6px 8px;
  }
  .barcode {
    flex: none;
    width: 52px;
    height: 18px;
    background: repeating-linear-gradient(90deg, #141414 0 2px, transparent 2px 4px, #141414 4px 7px, transparent 7px 9px);
  }
  .code { flex: 1; font-weight: 700; font-size: 13px; letter-spacing: 0.18em; }
  .copy {
    border: 2px solid #141414;
    background: #BCE740;
    font-family: inherit;
    font-weight: 900;
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 4px 8px;
    cursor: pointer;
    box-shadow: 2px 2px 0 #141414;
  }
  .copy:active { transform: translate(2px, 2px); box-shadow: none; }
  .stack {
    display: flex;
    align-items: center;
    gap: 8px;
    border-top: 2px dashed #141414;
    padding: 8px 12px;
    font-size: 11px;
    font-weight: 700;
  }
  .stack .cardname { flex: 1; min-width: 0; }
  .save {
    background: #141414;
    color: #BCE740;
    font-family: Archivo, 'Arial Black', sans-serif;
    font-weight: 900;
    font-size: 14px;
    padding: 4px 8px;
    white-space: nowrap;
  }
  .pill {
    display: none;
    align-items: center;
    gap: 8px;
    background: #FFF6E9;
    border: 2px solid #141414;
    box-shadow: 4px 4px 0 #141414;
    padding: 6px 10px;
    cursor: pointer;
    font-weight: 700;
    font-size: 12px;
    animation: lapse-slide-in 0.2s ease-out;
  }
  .wrap.collapsed .card { display: none; }
  .wrap.collapsed .pill { display: flex; }
`;

function showLapseSenseToast(lookup: LookupResult, domain: string, stack: StackResult | null): void {
  if (!document.body) return;

  const top = lookup.rewards[0];
  if (!top) return;
  const reward = top.reward;
  const merchant = lookup.merchant?.name || reward.merchant_name || domain;
  const days = top.days_until_expiry ?? daysUntilExpiry(reward.expires_at);
  const expiry = formatExpiry(days);
  const urgency = urgencyFromDays(days);
  const valueLabel = formatRewardValue(reward);
  const rewardCount = lookup.rewards.length;

  const host = document.createElement('div');
  host.setAttribute('data-testid', 'lapse-sense-toast');
  host.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:2147483647;';
  const shadow = host.attachShadow({ mode: 'closed' });

  const style = document.createElement('style');
  style.textContent = CSS;
  shadow.appendChild(style);

  const wrap = document.createElement('div');
  wrap.className = 'wrap';

  const card = document.createElement('div');
  card.className = 'card';
  card.setAttribute('data-part', 'card');

  /* header */
  const head = document.createElement('div');
  head.className = 'head';
  const brand = document.createElement('span');
  brand.className = 'brand';
  brand.textContent = '✂ LAPSE SENSE';
  head.appendChild(brand);
  if (rewardCount > 1) {
    const count = document.createElement('span');
    count.className = 'count';
    count.textContent = `${rewardCount} rewards here`;
    head.appendChild(count);
  }
  const close = document.createElement('button');
  close.className = 'close';
  close.type = 'button';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '×';
  head.appendChild(close);
  card.appendChild(head);

  /* main row: ring + merchant + big value */
  const main = document.createElement('div');
  main.className = 'main';
  const ringbox = document.createElement('div');
  ringbox.className = 'ringbox';
  ringbox.innerHTML = ringSvg(
    expiryFraction(reward.created_at, reward.expires_at),
    URGENCY_COLORS[urgency],
    40,
    5,
  );
  if (expiry) {
    const expires = document.createElement('div');
    expires.className = 'expires';
    expires.style.color = URGENCY_COLORS[urgency];
    expires.textContent = expiry;
    ringbox.appendChild(expires);
  }
  main.appendChild(ringbox);
  const text = document.createElement('div');
  text.className = 'text';
  const merchantEl = document.createElement('div');
  merchantEl.className = 'merchant';
  merchantEl.textContent = rewardCount > 1 ? `${merchant} · top reward` : merchant;
  const value = document.createElement('div');
  value.className = 'value';
  value.textContent = valueLabel;
  text.append(merchantEl, value);
  main.appendChild(text);
  card.appendChild(main);

  /* code strip */
  if (reward.code) {
    const codes = document.createElement('div');
    codes.className = 'codes';
    const barcode = document.createElement('span');
    barcode.className = 'barcode';
    const code = document.createElement('span');
    code.className = 'code';
    code.textContent = reward.code;
    const copy = document.createElement('button');
    copy.className = 'copy';
    copy.type = 'button';
    copy.textContent = 'Copy';
    copy.addEventListener('click', () => {
      const text = reward.code ?? '';
      const fallback = () => {
        const area = document.createElement('textarea');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
      };
      try {
        void navigator.clipboard.writeText(text).catch(fallback);
      } catch {
        fallback();
      }
      copy.textContent = 'Copied';
      window.setTimeout(() => {
        copy.textContent = 'Copy';
      }, 1500);
    });
    codes.append(barcode, code, copy);
    card.appendChild(codes);
  }

  /* stack preview: best card + savings, only when a cart total was found */
  if (stack?.recommended_card) {
    const row = document.createElement('div');
    row.className = 'stack';
    const cardname = document.createElement('span');
    cardname.className = 'cardname';
    cardname.textContent = `💳 ${stack.recommended_card.issuer} ${stack.recommended_card.name}`;
    row.appendChild(cardname);
    const save = document.createElement('span');
    save.className = 'save';
    save.setAttribute('data-part', 'save');
    save.textContent = `You save ${formatMoney(stack.total_savings)}`;
    row.appendChild(save);
    card.appendChild(row);
  }

  /* collapsed pill: ring + value, click to re-expand */
  const pill = document.createElement('button');
  pill.className = 'pill';
  pill.type = 'button';
  pill.setAttribute('data-part', 'pill');
  const pillRing = document.createElement('span');
  pillRing.innerHTML = ringSvg(
    expiryFraction(reward.created_at, reward.expires_at),
    URGENCY_COLORS[urgency],
    18,
    3,
  );
  const pillText = document.createElement('span');
  pillText.textContent = `✂ ${valueLabel} · ${merchant}`;
  pill.append(pillRing, pillText);

  wrap.append(card, pill);
  shadow.appendChild(wrap);
  document.body.appendChild(host);

  // Auto-collapse to the pill (not a full hide); the pill re-expands on click.
  let collapseTimer: number | null = window.setTimeout(() => {
    wrap.classList.add('collapsed');
  }, COLLAPSE_AFTER_MS);
  pill.addEventListener('click', () => {
    wrap.classList.remove('collapsed');
    if (collapseTimer !== null) window.clearTimeout(collapseTimer);
    collapseTimer = window.setTimeout(() => wrap.classList.add('collapsed'), COLLAPSE_AFTER_MS);
  });
  close.addEventListener('click', () => {
    if (collapseTimer !== null) window.clearTimeout(collapseTimer);
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
        .then(async (response) => {
          // PAGE_VISIT already answers with the lookup for this domain; reuse it.
          const result = response as RpcResult<LookupResult> | undefined;
          if (!result?.ok || sensedDomains.has(page.domain)) return;
          if (result.data.rewards.length < 1) return;
          sensedDomains.add(page.domain);

          // When the page exposes a cart total, preview the stack through the
          // background's existing CALCULATE_STACK path (/stack).
          let stack: StackResult | null = null;
          const cartTotal = detectCartTotal();
          if (cartTotal) {
            const stackResponse = (await browser.runtime
              .sendMessage({ type: 'CALCULATE_STACK', domain: page.domain, cartTotal })
              .catch(() => null)) as RpcResult<StackResult> | null;
            if (stackResponse?.ok) stack = stackResponse.data;
          }
          showLapseSenseToast(result.data, page.domain, stack);
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
