import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ExpiryRing } from '../components/ExpiryRing'
import { useRewards } from '../context/RewardsContext'
import type { SavingsItem } from '../api/savings'
import { addDays, dateKey, formatDate, formatMonthDay, startOfWeek } from '../util/dates'
import { formatDollars, fromCents, toCents } from '../util/money'

type SortKey = 'description' | 'saved' | 'merchant_name' | 'redeemed_at'

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'description', label: 'Item' },
  { key: 'saved', label: 'Saved' },
  { key: 'merchant_name', label: 'Store' },
  { key: 'redeemed_at', label: 'Date' },
]

/** Consecutive Monday-based weeks (ending this or last week) with a redemption. */
function savingsStreakWeeks(items: SavingsItem[], now = new Date()): number {
  if (items.length === 0) return 0
  const weeks = new Set(items.map((item) => dateKey(startOfWeek(new Date(item.redeemed_at)))))
  let cursor = startOfWeek(now)
  if (!weeks.has(dateKey(cursor))) cursor = addDays(cursor, -7)
  let streak = 0
  while (weeks.has(dateKey(cursor))) {
    streak += 1
    cursor = addDays(cursor, -7)
  }
  return streak
}

function monthlyTotals(items: SavingsItem[]): { key: string; label: string; cents: number }[] {
  const byMonth = new Map<string, number>()
  for (const item of items) {
    const key = item.redeemed_at.slice(0, 7)
    byMonth.set(key, (byMonth.get(key) ?? 0) + toCents(item.saved))
  }
  return [...byMonth.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, cents]) => ({
      key,
      label: new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)) - 1, 1)).toLocaleDateString(
        'en-US',
        { month: 'short', timeZone: 'UTC' },
      ),
      cents,
    }))
}

export function Savings() {
  const { savings, loading, error } = useRewards()
  const [sortKey, setSortKey] = useState<SortKey>('redeemed_at')
  const [direction, setDirection] = useState<'asc' | 'desc'>('desc')

  const rows = useMemo(() => {
    const items = [...(savings?.items ?? [])]
    items.sort((a, b) => compare(a, b, sortKey) * (direction === 'asc' ? 1 : -1))
    return items
  }, [savings, sortKey, direction])

  const series = useMemo(
    () =>
      (savings?.series ?? []).map((point) => ({
        date: point.date,
        cumulative: Number(point.cumulative),
      })),
    [savings],
  )

  const streak = useMemo(() => savingsStreakWeeks(savings?.items ?? []), [savings])
  const months = useMemo(() => monthlyTotals(savings?.items ?? []), [savings])
  const best = useMemo(() => {
    const items = savings?.items ?? []
    if (items.length === 0) return null
    return [...items].sort((a, b) => Number(b.saved) - Number(a.saved))[0]
  }, [savings])

  function toggle(key: SortKey) {
    if (key === sortKey) {
      setDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(key)
    setDirection(key === 'redeemed_at' || key === 'saved' ? 'desc' : 'asc')
  }

  return (
    <div>
      <Link
        to="/dashboard"
        className="inline-block border-2 border-line bg-white px-3 py-1 text-xs font-black uppercase text-ink shadow-card"
      >
        ← Back
      </Link>
      <h1 className="mt-5 font-display text-4xl font-black uppercase tracking-tight text-ink">Total savings</h1>
      {error ? <p className="mt-4 text-sm font-bold text-tangerine">{error}</p> : null}

      <div className="mt-6 grid grid-cols-1 items-start gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="rotate-[-0.6deg] border-2 border-line bg-tangerine p-5 text-white shadow-pop">
            <div className="text-xs font-black uppercase tracking-wider">Total kept from lapsing</div>
            <p data-testid="savings-total" className="font-display text-6xl font-black leading-none tracking-tight">
              {savings ? formatDollars(savings.total) : loading ? '—' : '$0.00'}
            </p>
            <div className="mt-2 inline-block bg-ink px-2 py-0.5 text-[11px] font-bold uppercase text-lime">
              {savings?.items.length ?? 0} coupons cashed
            </div>
          </div>

          <div className="border-2 border-line bg-white p-4 shadow-stamp">
            <div className="text-xs font-black uppercase tracking-wider text-ink">Streak</div>
            <div className="mt-1 flex items-center gap-3">
              <ExpiryRing fraction={1} urgency="later" size={44} stroke={6}>
                <span className="font-black text-ink">{streak}</span>
              </ExpiryRing>
              <div className="text-sm font-bold leading-tight text-ink">
                {streak === 1 ? '1 week' : `${streak} weeks`} in a row
                <br />
                <span className="font-semibold text-muted">with a redemption</span>
              </div>
            </div>
          </div>

          <div className="border-2 border-line bg-lilac p-4 shadow-stamp">
            <div className="text-xs font-black uppercase tracking-wider text-ink">By month</div>
            {months.length > 0 ? (
              <div className="mt-2">
                <MonthBars months={months} />
              </div>
            ) : (
              <p className="mt-2 text-sm font-semibold text-ink">No redemptions yet.</p>
            )}
          </div>

          <div className="border-2 border-line bg-white p-4 shadow-stamp">
            <div className="text-xs font-black uppercase tracking-wider text-ink">Best haul</div>
            {best ? (
              <div className="mt-1 font-display text-xl font-black text-ink">
                {formatDollars(best.saved)} <span className="text-sm font-bold">at {best.merchant_name}</span>
              </div>
            ) : (
              <p className="mt-1 text-sm font-semibold text-muted">Nothing cashed yet.</p>
            )}
          </div>
        </div>

        <div className="space-y-5">
          <section className="border-2 border-line bg-white p-4 shadow-pop">
            <h2 className="text-sm font-black uppercase tracking-wider text-ink">The pile grows</h2>
            <div className="mt-3 h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="#E3D5B8" strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={formatMonthDay} minTickGap={28} tick={{ fill: '#5a5a5a', fontSize: 12 }} />
                  <YAxis
                    domain={[0, 'auto']}
                    width={64}
                    tickFormatter={(value: number) => `$${value}`}
                    tick={{ fill: '#5a5a5a', fontSize: 12 }}
                  />
                  <Tooltip
                    formatter={(value) => [formatDollars(Number(value)), 'Saved']}
                    labelFormatter={(label) => formatMonthDay(String(label))}
                  />
                  <Area type="monotone" dataKey="cumulative" stroke="#141414" fill="#BCE740" fillOpacity={0.6} strokeWidth={2.5} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="overflow-hidden border-2 border-line bg-white shadow-pop">
            <table className="w-full text-left text-sm">
              <thead className="border-b-2 border-line bg-amber text-xs font-black uppercase text-ink">
                <tr>
                  {COLUMNS.map((column) => {
                    const active = sortKey === column.key
                    const arrow = active ? (direction === 'asc' ? '↑' : '↓') : ''
                    return (
                      <th key={column.key} className="px-4 py-2.5">
                        <button type="button" onClick={() => toggle(column.key)} className="inline-flex items-center gap-1 uppercase">
                          {column.label}
                          <span aria-hidden>{arrow}</span>
                          {active ? <span className="sr-only">{direction === 'asc' ? 'ascending' : 'descending'}</span> : null}
                        </button>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((item) => (
                  <tr
                    key={`${item.reward_id}-${item.redeemed_at}`}
                    className="border-b-2 border-dashed border-[#d9cdb2] font-semibold last:border-0"
                  >
                    <td className="px-4 py-2.5 text-ink">{item.description}</td>
                    <td className="px-4 py-2.5 font-black text-ink">{formatDollars(item.saved)}</td>
                    <td className="px-4 py-2.5 text-ink">{item.merchant_name}</td>
                    <td className="px-4 py-2.5 text-muted">{formatDate(item.redeemed_at)}</td>
                  </tr>
                ))}
                {rows.length === 0 && !loading ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center font-bold uppercase text-muted">
                      No savings yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  )
}

function MonthBars({ months }: { months: { key: string; label: string; cents: number }[] }) {
  const max = Math.max(...months.map((m) => m.cents), 1)
  return (
    <div className="flex items-end gap-3">
      {months.map((m) => (
        <div key={m.key} className="flex flex-col items-center gap-1">
          <span className="text-xs font-bold text-ink">{formatDollars(fromCents(m.cents))}</span>
          <div className="w-10 bg-ink" style={{ height: Math.max(12, (m.cents / max) * 72) }} />
          <span className="text-[10px] font-black uppercase tracking-wider text-ink">{m.label}</span>
        </div>
      ))}
    </div>
  )
}

function compare(a: SavingsItem, b: SavingsItem, key: SortKey): number {
  if (key === 'saved') return Number(a.saved) - Number(b.saved)
  if (key === 'redeemed_at') return a.redeemed_at.localeCompare(b.redeemed_at)
  return a[key].localeCompare(b[key])
}
