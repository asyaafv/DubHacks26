import { useState } from 'react';
import { formatMoney } from '../core/format';
import type { StackResult } from '../types';
import { CopyCode } from './CopyCode';

interface StackResultViewProps {
  stack: StackResult;
  onMarkUsed?: (rewardId: string, saved?: string) => Promise<void>;
}

export function StackResultView({ stack, onMarkUsed }: StackResultViewProps) {
  const card = stack.recommended_card;
  const coded = stack.chosen_rewards.filter((item) => Boolean(item.reward.code));
  const [used, setUsed] = useState<Record<string, 'pending' | 'done'>>({});

  async function markUsed(rewardId: string, saved?: string) {
    if (!onMarkUsed || used[rewardId]) return;
    setUsed((current) => ({ ...current, [rewardId]: 'pending' }));
    try {
      await onMarkUsed(rewardId, saved);
      setUsed((current) => ({ ...current, [rewardId]: 'done' }));
    } catch {
      setUsed((current) => {
        const next = { ...current };
        delete next[rewardId];
        return next;
      });
    }
  }

  return (
    <section className="rounded-xl bg-lapse px-3 py-3 text-white" data-testid="stack-result">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-white/70">Final price</div>
          <div className="text-xs text-white/60 line-through">{formatMoney(stack.original_price)}</div>
          <div className="text-2xl font-semibold leading-tight" data-testid="final-price">
            {formatMoney(stack.final_price)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[11px] uppercase tracking-wide text-white/70">Total savings</div>
          <div className="text-lg font-semibold" data-testid="total-savings">
            {formatMoney(stack.total_savings)}
          </div>
        </div>
      </div>
      {card ? (
        <p className="mt-3 text-sm" data-testid="recommended-card">
          {card.issuer} {card.name}
        </p>
      ) : null}
      <p className="mt-2 text-xs leading-5 text-white/90" data-testid="explanation">
        {stack.explanation}
      </p>
      {coded.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          {coded.map((item) => (
            <span key={item.reward_id} className="inline-flex items-center gap-2">
              <CopyCode code={item.reward.code!} tone="light" testId="stack-code" />
              {onMarkUsed ? (
                <button
                  type="button"
                  data-testid="mark-used"
                  disabled={Boolean(used[item.reward_id])}
                  onClick={() => void markUsed(item.reward_id, String(item.savings))}
                  className="mt-2 inline-flex items-center rounded-lg bg-white/15 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-white/80 hover:bg-white/25 disabled:opacity-80"
                >
                  {used[item.reward_id] === 'done'
                    ? 'Used'
                    : used[item.reward_id] === 'pending'
                      ? 'Marking…'
                      : 'Mark used'}
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
