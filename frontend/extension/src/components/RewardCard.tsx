import { formatExpiry, formatRewardValue, isExpiringSoon, money } from '../core/format';
import { saveForLaterLabel } from '../core/useFirst';
import type { ScoredReward } from '../types';
import { CopyCode } from './CopyCode';
import { ExpiryRing, expiryFraction, urgencyFromDays } from './ExpiryRing';
import { StoreLogo } from './StoreLogo';

function trimAmount(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export function RewardCard({ scored, domain = '' }: { scored: ScoredReward; domain?: string }) {
  const reward = scored.reward;
  const days = scored.days_until_expiry;
  const expiry = formatExpiry(days);
  const soon = isExpiringSoon(days);
  const minSpend = money(reward.min_spend);
  const exclusions = reward.exclusions?.length ? reward.exclusions.join(' / ').toLowerCase() : null;

  return (
    <article className="border-2 border-ink bg-white shadow-hard" data-testid="reward-card">
      <div className="flex items-center gap-2 border-b-2 border-dashed border-ink px-3 py-2">
        <StoreLogo domain={domain} name={reward.merchant_name} size="h-8 w-8" />
        <h3 className="min-w-0 flex-1 truncate text-sm font-black uppercase">{reward.merchant_name}</h3>
        <ExpiryRing fraction={expiryFraction(reward.created_at, reward.expires_at)} urgency={urgencyFromDays(days)} />
      </div>
      <div className="px-3 py-2">
        {scored.use_first ? (
          <span
            className="inline-block -rotate-1 border-2 border-ink bg-lapse px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-white"
            data-testid="use-first-pill"
          >
            Use first
          </span>
        ) : null}
        <div className="font-display text-2xl font-black leading-tight" data-testid="reward-value">
          {formatRewardValue(reward)}
        </div>
        {scored.use_first && scored.recommendation ? (
          <p className="mt-1 text-[11px] font-bold leading-4 text-lapse" data-testid="use-first-recommendation">
            {scored.recommendation}
          </p>
        ) : null}
        <p className="mt-0.5 text-[11px] font-semibold text-[#5a5a5a]">
          {expiry ? (
            <span data-testid="expiry" className={soon ? 'font-bold text-lapse' : ''}>
              {expiry}
            </span>
          ) : (
            <span>No expiration</span>
          )}
          {minSpend > 0 ? <span> · min ${trimAmount(minSpend)}</span> : null}
          {exclusions ? <span> · no {exclusions}</span> : null}
        </p>
      </div>
      {reward.code ? (
        <div className="flex items-center justify-between gap-2 border-t-2 border-ink bg-cream px-3 py-1.5">
          <span className="barcode h-5 w-16 shrink-0" aria-hidden="true" />
          <CopyCode code={reward.code} />
        </div>
      ) : null}
    </article>
  );
}

/** Compact row for a reward flagged save_for_later; the label wraps so it never truncates. */
export function SaveForLaterRow({ scored }: { scored: ScoredReward }) {
  const reward = scored.reward;
  return (
    <div
      className="flex items-center justify-between gap-2 border-2 border-dashed border-ink bg-white px-3 py-1.5"
      data-testid="save-for-later-row"
    >
      <span className="min-w-0 flex-1 text-[11px] font-bold leading-snug">{saveForLaterLabel(scored)}</span>
      {reward.code ? (
        <span className="shrink-0">
          <CopyCode code={reward.code} />
        </span>
      ) : null}
    </div>
  );
}
