import { useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatDate, formatMonthDay } from '../util/dates'
import { formatDollars } from '../util/money'
import {
  centsToDollars,
  merchantHistory,
  monthlyTotals,
  savingsStreakWeeks,
  useMockupData,
  type MockupData,
} from './data'
import { ExpiryRing } from './Ring'
import type { Theme } from './themes'

function useSavingsModel(data: MockupData) {
  return useMemo(() => {
    const items = [...data.savings.items].sort((a, b) => b.redeemed_at.localeCompare(a.redeemed_at))
    const series = data.savings.series.map((p) => ({ date: p.date, cumulative: Number(p.cumulative) }))
    const months = monthlyTotals(data.savings.items)
    const streak = savingsStreakWeeks(data.savings.items)
    const history = merchantHistory(data.savings.items)
    const best = [...data.savings.items].sort((a, b) => Number(b.saved) - Number(a.saved))[0]
    return { items, series, months, streak, history, best }
  }, [data])
}

function Chart({ data, theme, height = 280 }: { data: { date: string; cumulative: number }[]; theme: Theme; height?: number }) {
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`fill-${theme.id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.chart.fill} stopOpacity={theme.id === 'c' ? 0.5 : 0.45} />
              <stop offset="100%" stopColor={theme.chart.fill} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={theme.chart.grid} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="date" tickFormatter={formatMonthDay} minTickGap={28} tick={{ fill: theme.chart.tick, fontSize: 11 }} axisLine={{ stroke: theme.chart.grid }} tickLine={false} />
          <YAxis domain={[0, 'auto']} width={48} tickFormatter={(v: number) => `$${v}`} tick={{ fill: theme.chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip formatter={(value) => [formatDollars(Number(value)), 'Saved']} labelFormatter={(label) => formatMonthDay(String(label))} />
          <Area type="monotone" dataKey="cumulative" stroke={theme.chart.stroke} strokeWidth={2.5} fill={`url(#fill-${theme.id})`} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function MonthBars({ months, max, bar, label }: { months: { label: string; cents: number }[]; max: number; bar: string; label: string }) {
  return (
    <div className="flex items-end gap-3">
      {months.map((m) => (
        <div key={m.label} className="flex flex-col items-center gap-1">
          <span className={`text-xs font-semibold ${label}`}>{centsToDollars(m.cents)}</span>
          <div className="w-10 rounded-t" style={{ height: Math.max(12, (m.cents / max) * 72), background: bar }} />
          <span className={`text-[10px] uppercase tracking-wider ${label}`}>{m.label}</span>
        </div>
      ))}
    </div>
  )
}

/* A — Fieldnotes */
function SavingsA({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useSavingsModel(data)
  const max = Math.max(...m.months.map((x) => x.cents))
  return (
    <div className="min-h-screen bg-[#f8f8ef] text-[#1f3029] mock-grain" style={{ fontFamily: 'Inter, sans-serif' }}>
      <header className="border-b border-[#e0dcc8]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="font-serif text-2xl tracking-tight text-[#174b34]">Lapse</span>
          <span className="text-sm text-[#52705d]">← Back to rewards</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="font-serif text-4xl tracking-tight">You've kept {formatDollars(data.savings.total)} from lapsing.</h1>
            <p className="mt-2 text-sm text-[#52705d]">
              {data.savings.items.length} rewards used · biggest win {formatDollars(m.best.saved)} at {m.best.merchant_name}
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-[#e0dcc8] bg-white px-4 py-3 shadow-[4px_5px_0_#e6e2ce]">
            <ExpiryRing state={{ fraction: 1, daysLeft: null, urgency: 'later' }} theme={theme} size={40} stroke={4}>
              <span className="font-serif text-sm text-[#174b34]">{m.streak}</span>
            </ExpiryRing>
            <div className="text-sm">
              <div className="font-semibold">{m.streak}-week streak</div>
              <div className="text-xs text-[#6b7f72]">a redemption every week since Sep 8</div>
            </div>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-[minmax(0,1fr)_300px] gap-6">
          <section className="rounded-2xl border border-[#e0dcc8] bg-white p-5 shadow-[4px_5px_0_#e6e2ce]">
            <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8fa394]">Savings over time</h2>
            <Chart data={m.series} theme={theme} />
          </section>
          <div className="space-y-4">
            <section className="rounded-2xl border border-[#e0dcc8] bg-white p-5 shadow-[4px_5px_0_#e6e2ce]">
              <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8fa394]">By month</h2>
              <div className="mt-3"><MonthBars months={m.months} max={max} bar="#8fb58a" label="text-[#52705d]" /></div>
            </section>
            <section className="rounded-2xl border border-[#e0dcc8] bg-white p-5 shadow-[4px_5px_0_#e6e2ce]">
              <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8fa394]">Top stores</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {m.history.slice(0, 5).map((h) => (
                  <li key={h.merchant} className="flex justify-between">
                    <span>{h.merchant} <span className="text-xs text-[#8fa394]">×{h.count}</span></span>
                    <span className="font-serif text-[#174b34]">{centsToDollars(h.totalCents)}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>

        <section className="mt-6 overflow-hidden rounded-2xl border border-[#e0dcc8] bg-white shadow-[4px_5px_0_#e6e2ce]">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-[#e0dcc8] bg-[#f8f8ef] text-[#52705d]">
              <tr><th className="px-4 py-3 font-medium">Item</th><th className="px-4 py-3 font-medium">Saved</th><th className="px-4 py-3 font-medium">Store</th><th className="px-4 py-3 font-medium">Date</th></tr>
            </thead>
            <tbody>
              {m.items.slice(0, 5).map((item) => (
                <tr key={item.reward_id} className="border-b border-[#eeeadb] last:border-0">
                  <td className="px-4 py-2.5">{item.description}</td>
                  <td className="px-4 py-2.5 font-serif text-[#174b34]">{formatDollars(item.saved)}</td>
                  <td className="px-4 py-2.5">{item.merchant_name}</td>
                  <td className="px-4 py-2.5 text-[#6b7f72]">{formatDate(item.redeemed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  )
}

/* B — Clip & Save */
function SavingsB({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useSavingsModel(data)
  const max = Math.max(...m.months.map((x) => x.cents))
  return (
    <div className="min-h-screen bg-[#FFF6E9] text-[#141414]" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <header className="border-b-2 border-[#141414] bg-[#BCE740]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <span className="text-3xl font-black uppercase" style={{ fontFamily: 'Archivo, sans-serif' }}>Lapse / Savings</span>
          <span className="border-2 border-[#141414] bg-white px-3 py-1 text-xs font-black uppercase">← Rewards</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        <div className="grid grid-cols-[320px_minmax(0,1fr)] gap-5">
          <div className="space-y-4">
            <div className="rotate-[-0.6deg] border-2 border-[#141414] bg-[#FF5C1C] p-5 text-white" style={{ boxShadow: '8px 8px 0 #141414' }}>
              <div className="text-xs font-black uppercase tracking-wider">Total kept from lapsing</div>
              <div className="text-6xl font-black leading-none" style={{ fontFamily: 'Archivo, sans-serif' }}>{formatDollars(data.savings.total)}</div>
              <div className="mt-2 inline-block bg-[#141414] px-2 py-0.5 text-[11px] font-bold uppercase text-[#BCE740]">
                {data.savings.items.length} coupons cashed
              </div>
            </div>
            <div className="border-2 border-[#141414] bg-white p-4" style={{ boxShadow: '6px 6px 0 #141414' }}>
              <div className="text-xs font-black uppercase tracking-wider">Streak</div>
              <div className="mt-1 flex items-center gap-3">
                <ExpiryRing state={{ fraction: 1, daysLeft: null, urgency: 'later' }} theme={theme} size={44} stroke={6}>
                  <span className="font-black">{m.streak}</span>
                </ExpiryRing>
                <div className="text-sm font-bold leading-tight">{m.streak} weeks in a row<br /><span className="font-semibold text-[#5a5a5a]">since Sep 8</span></div>
              </div>
            </div>
            <div className="border-2 border-[#141414] bg-[#CBA6FF] p-4" style={{ boxShadow: '6px 6px 0 #141414' }}>
              <div className="text-xs font-black uppercase tracking-wider">By month</div>
              <div className="mt-2"><MonthBars months={m.months} max={max} bar="#141414" label="text-[#141414]" /></div>
            </div>
            <div className="border-2 border-[#141414] bg-white p-4" style={{ boxShadow: '6px 6px 0 #141414' }}>
              <div className="text-xs font-black uppercase tracking-wider">Best haul</div>
              <div className="mt-1 text-xl font-black" style={{ fontFamily: 'Archivo, sans-serif' }}>
                {formatDollars(m.best.saved)} <span className="text-sm font-bold">at {m.best.merchant_name}</span>
              </div>
            </div>
          </div>

          <div className="space-y-5">
            <section className="border-2 border-[#141414] bg-white p-4" style={{ boxShadow: '8px 8px 0 #141414' }}>
              <h2 className="text-sm font-black uppercase tracking-wider">The pile grows</h2>
              <Chart data={m.series} theme={theme} height={230} />
            </section>
            <section className="border-2 border-[#141414] bg-white" style={{ boxShadow: '8px 8px 0 #141414' }}>
              <table className="w-full text-left text-sm">
                <thead className="border-b-2 border-[#141414] bg-[#F5A800] text-xs font-black uppercase">
                  <tr><th className="px-4 py-2.5">Item</th><th className="px-4 py-2.5">Saved</th><th className="px-4 py-2.5">Store</th><th className="px-4 py-2.5">Date</th></tr>
                </thead>
                <tbody>
                  {m.items.slice(0, 6).map((item) => (
                    <tr key={item.reward_id} className="border-b-2 border-dashed border-[#d9cdb2] font-semibold last:border-0">
                      <td className="px-4 py-2">{item.description}</td>
                      <td className="px-4 py-2 font-black">{formatDollars(item.saved)}</td>
                      <td className="px-4 py-2">{item.merchant_name}</td>
                      <td className="px-4 py-2 text-[#5a5a5a]">{formatDate(item.redeemed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>
        </div>
      </main>
    </div>
  )
}

/* C — Night Vault */
function SavingsC({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useSavingsModel(data)
  const max = Math.max(...m.months.map((x) => x.cents))
  return (
    <div className="min-h-screen bg-[#0A1310] text-[#E7F4EC] mock-scanlines" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <header className="border-b border-[#1D3127]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-xl font-semibold text-[#3DDC97]">Lapse — Savings ledger</span>
          <span className="font-mono text-xs text-[#6FA08A]">GET /savings · user 0000…0001</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-7">
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Total saved</div>
            <div className="mt-1 font-mono text-4xl font-bold text-[#3DDC97]" style={{ textShadow: '0 0 20px rgba(61,220,151,0.4)' }}>{formatDollars(data.savings.total)}</div>
          </div>
          <div className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Redemptions</div>
            <div className="mt-1 font-mono text-4xl font-bold">{data.savings.items.length}</div>
          </div>
          <div className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Weekly streak</div>
            <div className="mt-1 flex items-center gap-2">
              <ExpiryRing state={{ fraction: 1, daysLeft: null, urgency: 'later' }} theme={theme} size={34} stroke={4}>
                <span className="font-mono text-xs font-bold text-[#3DDC97]">{m.streak}</span>
              </ExpiryRing>
              <span className="font-mono text-sm text-[#9DBCA9]">wk × {m.streak}</span>
            </div>
          </div>
          <div className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
            <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Best single save</div>
            <div className="mt-1 font-mono text-2xl font-bold text-[#FFC24B]">{formatDollars(m.best.saved)}</div>
            <div className="font-mono text-[11px] text-[#9DBCA9]">{m.best.merchant_name}</div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-[minmax(0,1fr)_280px] gap-5">
          <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-5">
            <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Cumulative savings — 6 weeks</h2>
            <Chart data={m.series} theme={theme} height={240} />
          </section>
          <div className="space-y-4">
            <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
              <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Monthly</h2>
              <div className="mt-3"><MonthBars months={m.months} max={max} bar="#3DDC97" label="text-[#9DBCA9]" /></div>
            </section>
            <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
              <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">By merchant</h2>
              <ul className="mt-2 space-y-1.5 font-mono text-xs">
                {m.history.slice(0, 6).map((h) => (
                  <li key={h.merchant} className="flex justify-between">
                    <span className="text-[#9DBCA9]">{h.merchant} ×{h.count}</span>
                    <span className="text-[#3DDC97]">{centsToDollars(h.totalCents)}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>

        <section className="mt-5 overflow-hidden rounded-xl border border-[#1D3127] bg-[#0E1A14]">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-[#1D3127] bg-[#122019] uppercase tracking-widest text-[#6FA08A]">
              <tr><th className="px-4 py-2.5">Item</th><th className="px-4 py-2.5">Saved</th><th className="px-4 py-2.5">Store</th><th className="px-4 py-2.5">Date</th></tr>
            </thead>
            <tbody>
              {m.items.slice(0, 5).map((item) => (
                <tr key={item.reward_id} className="border-b border-[#16261E] last:border-0">
                  <td className="px-4 py-2 text-[#E7F4EC]">{item.description}</td>
                  <td className="px-4 py-2 text-[#3DDC97]">{formatDollars(item.saved)}</td>
                  <td className="px-4 py-2 text-[#9DBCA9]">{item.merchant_name}</td>
                  <td className="px-4 py-2 text-[#6FA08A]">{formatDate(item.redeemed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  )
}

export function MockSavings({ theme }: { theme: Theme }) {
  const data = useMockupData()
  if (!data) return null
  if (theme.id === 'b') return <SavingsB data={data} theme={theme} />
  if (theme.id === 'c') return <SavingsC data={data} theme={theme} />
  return <SavingsA data={data} theme={theme} />
}
