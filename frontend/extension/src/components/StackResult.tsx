import { formatMoney } from '../core/format';
import type { StackResult } from '../types';
import { CopyCode } from './CopyCode';

export function StackResultView({ stack }: { stack: StackResult }) {
  const card = stack.recommended_card;
  const codes = stack.chosen_rewards
    .map((item) => item.reward.code)
    .filter((code): code is string => Boolean(code));

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
      {codes.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {codes.map((code) => (
            <CopyCode key={code} code={code} tone="light" testId="stack-code" />
          ))}
        </div>
      ) : null}
    </section>
  );
}
