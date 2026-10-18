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
    <div className="flex flex-col gap-3 bg-cream p-4 font-sans text-ink">
      <header className="flex items-center justify-between gap-2 border-2 border-ink bg-lapse px-3 py-2 shadow-card">
        <span className="font-display text-xl font-black uppercase leading-none tracking-tight text-white">Lapse</span>
        <span className="max-w-[200px] truncate bg-ink px-2 py-0.5 text-[9px] font-bold uppercase text-lime">
          {page.domain ? `on ${page.domain}` : DEMO_USER_EMAIL}
        </span>
      </header>

      {events.toasts.map((toast) => (
        <ToastBanner key={toast.id} toast={toast} onDismiss={() => events.dismiss(toast.id)} />
      ))}

      {page.loading ? (
        <p className="border-2 border-ink bg-white px-3 py-2 text-xs font-bold uppercase shadow-card">Checking this store…</p>
      ) : null}

      {!page.loading && page.error ? (
        <p className="border-2 border-ink bg-white px-3 py-2 text-xs font-bold text-lapse shadow-card">{page.error}</p>
      ) : null}

      {!page.loading && !page.domain ? (
        <p className="border-2 border-ink bg-white px-3 py-4 text-sm font-semibold shadow-card">
          Open a store to see rewards.
        </p>
      ) : null}

      {!page.loading && page.domain ? (
        <>
          <section className="flex items-center gap-3 border-2 border-ink bg-white px-3 py-2.5 shadow-card">
            <StoreLogo domain={logoDomain} name={name} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h2 className="truncate font-display text-sm font-black uppercase" data-testid="store-name">
                  {name}
                </h2>
                {page.isCheckout ? (
                  <span
                    className="rotate-2 border-2 border-ink bg-amber px-1.5 py-0.5 text-[9px] font-black uppercase"
                    data-testid="checkout-pill"
                  >
                    Cart
                  </span>
                ) : null}
              </div>
              <p className="truncate text-xs font-semibold text-[#5a5a5a]" data-testid="store-domain">
                {logoDomain}
              </p>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            {rewards.length > 0 ? (
              rewards.map((scored) => <RewardCard key={scored.reward.id} scored={scored} domain={logoDomain} />)
            ) : (
              <p className="border-2 border-ink bg-white px-3 py-4 text-sm font-semibold shadow-card">
                No rewards for this store yet.
              </p>
            )}
          </section>

          <form
            className="border-2 border-ink bg-white p-3 shadow-card"
            onSubmit={(event) => {
              event.preventDefault();
              void stack.calculate();
            }}
          >
            <label htmlFor="cart-total" className="text-[10px] font-black uppercase tracking-widest">
              Cart total
            </label>
            <input
              id="cart-total"
              data-testid="cart-total"
              inputMode="decimal"
              placeholder="0.00"
              value={stack.cartTotal}
              onChange={(event) => stack.setCartTotal(event.target.value)}
              className="mt-1 w-full border-2 border-ink bg-cream px-2 py-1.5 text-sm font-semibold outline-none focus:bg-white"
            />
            <button
              type="submit"
              data-testid="stack-button"
              disabled={stack.stacking}
              className="mt-2 w-full border-2 border-ink bg-lapse px-3 py-2 text-sm font-black uppercase text-white shadow-card disabled:opacity-60"
            >
              {stack.stacking ? 'Calculating…' : 'Find best stack'}
            </button>
            {stack.error ? <p className="mt-2 text-xs font-bold text-lapse">{stack.error}</p> : null}
          </form>

          {stack.stack ? <StackResultView stack={stack.stack} onMarkUsed={stack.markUsed} /> : null}
        </>
      ) : null}

      <button
        type="button"
        data-testid="open-dashboard"
        onClick={openDashboard}
        className="py-1 text-center text-[10px] font-bold uppercase tracking-widest text-[#5a5a5a] hover:text-ink"
      >
        {DEMO_USER_EMAIL} · Open dashboard
      </button>
    </div>
  );
}
