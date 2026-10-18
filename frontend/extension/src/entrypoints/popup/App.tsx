import { DEMO_USER_EMAIL } from '../../api/config';
import { RewardCard } from '../../components/RewardCard';
import { StackResultView } from '../../components/StackResult';
import { StoreLogo } from '../../components/StoreLogo';
import { ToastBanner } from '../../components/ToastBanner';
import { useEvents } from '../../hooks/useEvents';
import { useRewards } from '../../hooks/useRewards';
import { useStack } from '../../hooks/useStack';
import { openDashboard } from '../../core/runtime';
import type { LookupResult } from '../../types';

function storeName(lookup: LookupResult | null, domain: string): string {
  return lookup?.merchant?.name || domain;
}

export default function App() {
  const page = useRewards();
  const stack = useStack(page.domain);
  const events = useEvents();
  const name = storeName(page.lookup, page.domain);
  const logoDomain = page.lookup?.merchant?.domain || page.domain;
  const rewards = page.lookup?.rewards.slice(0, 3) ?? [];

  return (
    <div className="flex flex-col gap-3 p-4">
      <header className="flex items-center gap-2">
        <img src="/icon/32.png" alt="" className="h-8 w-8" />
        <div>
          <div className="text-base font-semibold leading-none text-lapse">Lapse</div>
          <div className="mt-1 text-[11px] text-stone-500">{DEMO_USER_EMAIL}</div>
        </div>
      </header>

      {events.toasts.map((toast) => (
        <ToastBanner key={toast.id} toast={toast} onDismiss={() => events.dismiss(toast.id)} />
      ))}

      {page.loading ? <p className="text-sm text-stone-500">Checking this store…</p> : null}

      {!page.loading && page.error ? <p className="text-sm text-red-700">{page.error}</p> : null}

      {!page.loading && !page.domain ? (
        <p className="rounded-xl bg-white px-3 py-4 text-sm text-stone-600">Open a store to see rewards.</p>
      ) : null}

      {!page.loading && page.domain ? (
        <>
          <section className="flex items-center gap-3 rounded-xl bg-white px-3 py-3 shadow-sm ring-1 ring-black/5">
            <StoreLogo domain={logoDomain} name={name} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="truncate text-sm font-semibold" data-testid="store-name">
                  {name}
                </h2>
                {page.isCheckout ? (
                  <span
                    className="rounded-full bg-lapse/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-lapse"
                    data-testid="checkout-pill"
                  >
                    Cart
                  </span>
                ) : null}
              </div>
              <p className="truncate text-xs text-stone-500" data-testid="store-domain">
                {logoDomain}
              </p>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            {rewards.length > 0 ? (
              rewards.map((scored) => <RewardCard key={scored.reward.id} scored={scored} />)
            ) : (
              <p className="rounded-xl bg-white px-3 py-4 text-sm text-stone-600">No rewards for this store yet.</p>
            )}
          </section>

          <form
            className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-black/5"
            onSubmit={(event) => {
              event.preventDefault();
              void stack.calculate();
            }}
          >
            <label htmlFor="cart-total" className="text-xs font-medium text-stone-600">
              Cart total
            </label>
            <input
              id="cart-total"
              data-testid="cart-total"
              inputMode="decimal"
              placeholder="0.00"
              value={stack.cartTotal}
              onChange={(event) => stack.setCartTotal(event.target.value)}
              className="mt-1 w-full rounded-lg border border-stone-200 px-2 py-1.5 text-sm outline-none focus:border-lapse"
            />
            <button
              type="submit"
              data-testid="stack-button"
              disabled={stack.stacking}
              className="mt-2 w-full rounded-lg bg-lapse px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {stack.stacking ? 'Calculating…' : 'Find best stack'}
            </button>
            {stack.error ? <p className="mt-2 text-xs text-red-700">{stack.error}</p> : null}
          </form>

          {stack.stack ? <StackResultView stack={stack.stack} onMarkUsed={stack.markUsed} /> : null}
        </>
      ) : null}

      <button
        type="button"
        data-testid="open-dashboard"
        onClick={openDashboard}
        className="rounded-lg border border-lapse/30 bg-white px-3 py-2 text-sm font-medium text-lapse"
      >
        Open dashboard
      </button>
    </div>
  );
}
