import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useRewards } from '../context/RewardsContext'
import type { SavingsItem } from '../api/savings'
import { formatDate, formatMonthDay } from '../util/dates'
import { formatDollars } from '../util/money'

type SortKey = 'description' | 'saved' | 'merchant_name' | 'redeemed_at'

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'description', label: 'Item' },
  { key: 'saved', label: 'Saved' },
  { key: 'merchant_name', label: 'Store' },
  { key: 'redeemed_at', label: 'Date' },
]

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
      <Link to="/dashboard" className="text-sm font-semibold text-accent">
        ← Back
      </Link>
      <h1 className="mt-4 font-serif text-4xl text-ink">Total savings</h1>
      <p data-testid="savings-total" className="mt-3 font-serif text-5xl tracking-tight text-ink">
        {savings ? formatDollars(savings.total) : loading ? '—' : '$0.00'}
      </p>
      {error ? <p className="mt-4 text-sm text-rose-700">{error}</p> : null}

      <section className="mt-8 rounded-2xl border border-line bg-white p-5 shadow-card">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted">Savings over time</h2>
        <div className="mt-4 h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#E3DED2" strokeDasharray="3 3" />
              <XAxis dataKey="date" tickFormatter={formatMonthDay} minTickGap={28} tick={{ fill: '#5E7368', fontSize: 12 }} />
              <YAxis
                domain={[0, 'auto']}
                width={64}
                tickFormatter={(value: number) => `$${value}`}
                tick={{ fill: '#5E7368', fontSize: 12 }}
              />
              <Tooltip
                formatter={(value) => [formatDollars(Number(value)), 'Saved']}
                labelFormatter={(label) => formatMonthDay(String(label))}
              />
              <Area type="monotone" dataKey="cumulative" stroke="#1B6B45" fill="#1B6B45" fillOpacity={0.16} strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="mt-6 overflow-hidden rounded-2xl border border-line bg-white shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line bg-paper text-muted">
            <tr>
              {COLUMNS.map((column) => {
                const active = sortKey === column.key
                const arrow = active ? (direction === 'asc' ? '↑' : '↓') : ''
                return (
                  <th key={column.key} className="px-4 py-3 font-medium">
                    <button type="button" onClick={() => toggle(column.key)} className="inline-flex items-center gap-1">
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
              <tr key={`${item.reward_id}-${item.redeemed_at}`} className="border-b border-line last:border-0">
                <td className="px-4 py-3 text-ink">{item.description}</td>
                <td className="px-4 py-3 font-medium text-ink">{formatDollars(item.saved)}</td>
                <td className="px-4 py-3 text-ink">{item.merchant_name}</td>
                <td className="px-4 py-3 text-muted">{formatDate(item.redeemed_at)}</td>
              </tr>
            ))}
            {rows.length === 0 && !loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-muted">
                  No savings yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </div>
  )
}

function compare(a: SavingsItem, b: SavingsItem, key: SortKey): number {
  if (key === 'saved') return Number(a.saved) - Number(b.saved)
  if (key === 'redeemed_at') return a.redeemed_at.localeCompare(b.redeemed_at)
  return a[key].localeCompare(b[key])
}
