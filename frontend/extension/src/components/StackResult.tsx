import { useState } from 'react';
import { formatMoney, formatRewardValue, money } from '../core/format';
import type { StackResult } from '../types';
import { CopyCode } from './CopyCode';

interface StackResultViewProps {
  stack: StackResult;
  onMarkUsed?: (rewardId: string, saved?: string) => Promise<void>;
}

function trimPercent(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function StackResultView({ stack, onMarkUsed }: StackResultViewProps) {
  const card = stack.recommended_card;
  const coded = stack.chosen_rewards.filter((item) => Boolean(item.reward.code));
  const [used, setUsed] = useState<Record<string, 'pending' | 'done'>>({});

  const cashback = money(stack.card_cashback ?? 0);
  const finalPrice = money(stack.final_price);
  // Effective card rate on this purchase; fall back to the card's base rate.
  const cardRate = card
    ? finalPrice > 0 && cashback > 0
      ? trimPercent((cashback / finalPrice) * 100)
      : trimPercent(money(card.base_rate))
    : null;

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
    <section className="border-2 border-ink bg-ink p-3 text-white shadow-[5px_5px_0_#FF5C1C]" data-testid="stack-result">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[9px] font-black uppercase tracking-widest text-lime">You pay</div>
          <div className="text-[11px] text-white/50 line-through">{formatMoney(stack.original_price)}</div>
          <div className="font-display text-4xl font-black leading-none text-lime" data-testid="final-price">
            {formatMoney(stack.final_price)}
          </div>
        </div>
        <div className="rotate-3 border-2 border-lime px-2 py-1 text-center">
          <div className="text-[9px] font-black uppercase">Saved</div>
          <div className="text-xl font-black leading-tight text-lime" data-testid="total-savings">
            {formatMoney(stack.total_savings)}
          </div>
          <div className="text-[9px] font-bold">{trimPercent(money(stack.savings_percent))}%</div>
        </div>
      </div>

      <div className="mt-3 space-y-1 border-t-2 border-dashed border-white/30 pt-2">
        {stack.chosen_rewards.map((item) => (
          <div key={item.reward_id} className="flex items-center justify-between gap-2 text-xs font-bold">
            <span className="truncate">
              ✂ {item.reward.code ? `${item.reward.code} — ` : ''}
              {formatRewardValue(item.reward)}
            </span>
            <span className="shrink-0">−{formatMoney(item.savings)}</span>
          </div>
        ))}
        {card ? (
          <div className="flex items-center justify-between gap-2 text-xs font-bold text-sky" data-testid="recommended-card">
            <span className="truncate">
              💳 {card.issuer} {card.name} {cardRate}%
            </span>
            <span className="shrink-0">+{formatMoney(cashback)}</span>
          </div>
        ) : null}
      </div>

      <p className="mt-2 text-[11px] leading-4 text-white/70" data-testid="explanation">
        {stack.explanation}
      </p>

      {coded.length > 0 ? (
        <div className="mt-3 flex flex-col gap-2">
          {coded.map((item) => (
            <div key={item.reward_id} className="flex flex-col gap-2">
              <div className="self-start">
                <CopyCode code={item.reward.code!} tone="light" testId="stack-code" />
              </div>
              {onMarkUsed ? (
                <button
                  type="button"
                  data-testid="mark-used"
                  disabled={Boolean(used[item.reward_id])}
                  onClick={() => void markUsed(item.reward_id, String(item.savings))}
                  className="w-full border-2 border-lime bg-lime py-2 text-sm font-black uppercase text-ink disabled:opacity-70"
                >
                  {used[item.reward_id] === 'done'
                    ? 'Used ✓'
                    : used[item.reward_id] === 'pending'
                      ? 'Marking…'
                      : `Stack it → pay ${formatMoney(stack.final_price)}`}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
