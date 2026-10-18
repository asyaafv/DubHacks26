import { Fragment } from 'react';
import { formatExpiry, formatRewardValue, money } from '../core/format';
import type { SearchState } from '../hooks/useSearch';
import type { SearchHit } from '../types';
import { CopyCode } from './CopyCode';

/**
 * Reward search panel: input, quick chips from the user's own categories, and
 * ranked results with value, expiry, code and match reason. Owns no state —
 * App passes the useSearch() state in so it can also react to the query.
 * Direction B "Clip & Save" styling.
 */
export function SearchPanel({ search }: { search: SearchState }) {
  return (
    <section className="border-2 border-ink bg-white p-3 shadow-card" data-testid="search-panel">
      <label
        htmlFor="reward-search"
        className="font-display text-[11px] font-black uppercase tracking-wider text-ink"
      >
        Search your coupons
      </label>
      <input
        id="reward-search"
        data-testid="search-input"
        type="search"
        placeholder='Try "mexican food" or "streetwear"'
        value={search.query}
        onChange={(event) => search.setQuery(event.target.value)}
        className="mt-1 w-full border-2 border-ink bg-cream px-2 py-1.5 text-sm font-semibold outline-none placeholder:font-normal placeholder:text-muted focus:bg-white"
      />

      {search.chips.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5" data-testid="search-chips">
          {search.chips.slice(0, 6).map((chip) => (
            <button
              key={chip.label}
              type="button"
              data-testid={`chip-${chip.query}`}
              onClick={() => search.setQuery(chip.query)}
              className={`border-2 border-ink px-2 py-0.5 text-[11px] font-bold uppercase ${
                search.query.trim() === chip.query
                  ? 'bg-ink text-lime'
                  : 'bg-white text-ink hover:bg-lime'
              }`}
            >
              {chip.label} · {chip.count}
            </button>
          ))}
        </div>
      ) : null}

      {search.loading ? <p className="mt-2 text-xs font-semibold text-muted">Searching…</p> : null}
      {!search.loading && search.error ? (
        <p className="mt-2 text-xs font-bold text-lapse" data-testid="search-error">
          {search.error}
        </p>
      ) : null}
      {!search.loading && !search.error && search.results?.length === 0 ? (
        <p className="mt-2 text-xs font-semibold text-muted" data-testid="search-empty">
          No matching rewards. Try a broader term like “food” or “clothing”.
        </p>
      ) : null}

      {!search.loading && search.results?.length ? (
        <ul className="mt-2 flex flex-col gap-2" data-testid="search-results">
          {search.results.map((hit, index) => (
            <Fragment key={hit.reward.id}>
              {hit.secondary && !search.results![index - 1]?.secondary ? (
                <li
                  className="mt-1 flex items-center gap-2 font-display text-[10px] font-black uppercase tracking-wider text-ink"
                  data-testid="search-divider"
                >
                  <span className="flex-1 border-t-2 border-dashed border-ink" aria-hidden />
                  ✂ {search.secondaryLabel ?? 'More matches'}
                  <span className="flex-1 border-t-2 border-dashed border-ink" aria-hidden />
                </li>
              ) : null}
              <SearchResultRow hit={hit} />
            </Fragment>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function SearchResultRow({ hit }: { hit: SearchHit }) {
  const expiry = formatExpiry(hit.days_until_expiry);
  return (
    <li
      className="border-2 border-ink bg-cream px-2.5 py-2 shadow-[3px_3px_0_#141414]"
      data-testid="search-result"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="block truncate text-xs font-black uppercase tracking-wide text-ink">
            {hit.reward.merchant_name}
          </span>
          <span className="font-display text-lg font-black leading-tight text-ink">
            {formatRewardValue(hit.reward)}
          </span>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {hit.expiring_soon ? (
            <span
              className="rotate-2 border-2 border-ink bg-lapse px-1.5 py-0.5 text-[9px] font-black uppercase text-white"
              data-testid="expiring-soon"
            >
              Expiring soon
            </span>
          ) : null}
          {expiry ? <span className="text-[11px] font-semibold text-muted">{expiry}</span> : null}
        </div>
      </div>
      <p className="mt-1 text-[11px] font-semibold text-muted" data-testid="search-reason">
        {hit.reason}
      </p>
      {hit.best_card ? (
        <p className="mt-0.5 inline-block bg-lime px-1.5 py-0.5 text-[10px] font-bold uppercase text-ink" data-testid="best-card">
          Pair with {hit.best_card.name} · {money(hit.best_card.rate)}% back
        </p>
      ) : null}
      {hit.reward.code ? <CopyCode code={hit.reward.code} testId="search-code" /> : null}
    </li>
  );
}
