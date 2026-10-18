import { formatExpiry, formatRewardValue, isExpiringSoon } from '../core/format';
import type { ScoredReward } from '../types';
import { CopyCode } from './CopyCode';

export function RewardCard({ scored }: { scored: ScoredReward }) {
  const days = scored.days_until_expiry;
  const expiry = formatExpiry(days);
  const soon = isExpiringSoon(days);

  return (
    <article className="rounded-xl bg-white px-3 py-2.5 shadow-sm ring-1 ring-black/5" data-testid="reward-card">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-stone-900" data-testid="reward-value">
          {formatRewardValue(scored.reward)}
        </h3>
        {expiry ? (
          <p
            data-testid="expiry"
            className={`text-right text-xs font-medium ${soon ? 'text-red-700' : 'text-stone-500'}`}
          >
            {expiry}
          </p>
        ) : (
          <p className="text-xs text-stone-400">No expiration</p>
        )}
      </div>
      {scored.reward.code ? <CopyCode code={scored.reward.code} /> : null}
    </article>
  );
}
