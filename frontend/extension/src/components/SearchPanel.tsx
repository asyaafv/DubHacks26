import { formatExpiry, formatRewardValue, money } from '../core/format';
import { useSearch } from '../hooks/useSearch';
import type { SearchHit } from '../types';
import { CopyCode } from './CopyCode';

/**
 * Self-contained reward search: input, quick chips from the user's own
 * categories, and ranked results with value, expiry, code and match reason.
 * Styling mirrors the existing popup cards so a redesign can restyle in place.
 */
export function SearchPanel() {
  const search = useSearch();

  return (
    <section className="rounded-xl bg-white p-3 shadow-sm ring-1 ring-black/5" data-testid="search-panel">
      <label htmlFor="reward-search" className="text-xs font-medium text-stone-600">
        Search your rewards
      </label>
      <input
        id="reward-search"
        data-testid="search-input"
        type="search"
        placeholder='Try "mexican food" or "streetwear"'
        value={search.query}
        onChange={(event) => search.setQuery(event.target.value)}
        className="mt-1 w-full rounded-lg border border-stone-200 px-2 py-1.5 text-sm outline-none focus:border-lapse"
      />

      {search.chips.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5" data-testid="search-chips">
          {search.chips.slice(0, 6).map((chip) => (
            <button
              key={chip.label}
              type="button"
              data-testid={`chip-${chip.query}`}
              onClick={() => search.setQuery(chip.query)}
              className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                search.query.trim() === chip.query
                  ? 'bg-lapse text-white'
                  : 'bg-stone-100 text-stone-600 hover:bg-stone-200'
              }`}
            >
              {chip.label} · {chip.count}
            </button>
          ))}
        </div>
      ) : null}

      {search.loading ? <p className="mt-2 text-xs text-stone-500">Searching…</p> : null}
      {!search.loading && search.error ? (
        <p className="mt-2 text-xs text-red-700" data-testid="search-error">
          {search.error}
        </p>
      ) : null}
      {!search.loading && !search.error && search.results?.length === 0 ? (
        <p className="mt-2 text-xs text-stone-500" data-testid="search-empty">
          No matching rewards. Try a broader term like “food” or “clothing”.
        </p>
      ) : null}

      {!search.loading && search.results?.length ? (
        <ul className="mt-2 flex flex-col gap-2" data-testid="search-results">
          {search.results.map((hit) => (
            <SearchResultRow key={hit.reward.id} hit={hit} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function SearchResultRow({ hit }: { hit: SearchHit }) {
  const expiry = formatExpiry(hit.days_until_expiry);
  return (
    <li className="rounded-lg bg-stone-50 px-2.5 py-2 ring-1 ring-black/5" data-testid="search-result">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="block truncate text-sm font-semibold text-stone-900">
            {hit.reward.merchant_name}
          </span>
          <span className="text-sm text-stone-700">{formatRewardValue(hit.reward)}</span>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {hit.expiring_soon ? (
            <span
              className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-700"
              data-testid="expiring-soon"
            >
              Expiring soon
            </span>
          ) : null}
          {expiry ? <span className="text-[11px] text-stone-500">{expiry}</span> : null}
        </div>
      </div>
      <p className="mt-1 text-[11px] text-stone-500" data-testid="search-reason">
        {hit.reason}
      </p>
      {hit.best_card ? (
        <p className="mt-0.5 text-[11px] text-stone-500" data-testid="best-card">
          Pair with {hit.best_card.name} · {money(hit.best_card.rate)}% back
        </p>
      ) : null}
      {hit.reward.code ? <CopyCode code={hit.reward.code} testId="search-code" /> : null}
    </li>
  );
}
