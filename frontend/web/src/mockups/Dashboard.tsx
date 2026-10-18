import { useMemo } from 'react'
import { Area, AreaChart, ResponsiveContainer } from 'recharts'
import type { Reward } from '../types'
import { formatDollars } from '../util/money'
import {
  BUCKETS,
  formatExpiry,
  formatRewardValue,
  groupRewards,
  isOpenReward,
  needsReview,
} from '../util/rewards'
import { DEMO_USER } from '../util/demo'
import {
  bestCardFor,
  centsToDollars,
  lapsingSoon,
  merchantHistory,
  NOW,
  ringState,
  SOURCE_LABEL,
  useMockupData,
  type MockupData,
} from './data'
import { ExpiryRing, RingDays } from './Ring'
import type { Theme } from './themes'

const MONO_COLORS = ['#174b34', '#C2452D', '#B98A2F', '#52705d', '#8a5a2d', '#44607a']

function hue(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 997
  return MONO_COLORS[h % MONO_COLORS.length]
}

function Monogram({ name, theme, size = 40 }: { name: string; theme: Theme; size?: number }) {
  const letter = name.trim().charAt(0).toUpperCase()
  if (theme.id === 'b') {
    return (
      <div
        className="grid shrink-0 place-items-center border-2 border-[#141414] bg-white font-black"
        style={{ width: size, height: size, fontFamily: 'Archivo, sans-serif', boxShadow: '3px 3px 0 #141414' }}
      >
        {letter}
      </div>
    )
  }
  if (theme.id === 'c') {
    return (
      <div
        className="grid shrink-0 place-items-center rounded-lg border border-[#2A4335] bg-[#16261E] font-semibold text-[#3DDC97]"
        style={{ width: size, height: size }}
      >
        {letter}
      </div>
    )
  }
  return (
    <div
      className="grid shrink-0 place-items-center rounded-full font-serif text-white"
      style={{ width: size, height: size, background: hue(name) }}
    >
      {letter}
    </div>
  )
}

function useDashboardModel(data: MockupData) {
  return useMemo(() => {
    const open = data.sync.rewards.filter(isOpenReward)
    const groups = groupRewards(open)
    const nudges = lapsingSoon(open, 3)
    const history = merchantHistory(data.savings.items)
    const series = data.savings.series.map((p) => ({ date: p.date, cumulative: Number(p.cumulative) }))
    return { open, groups, nudges, history, series, wallet: data.sync.wallet }
  }, [data])
}

/* ================================================================== */
/* A — Fieldnotes                                                      */
/* ================================================================== */

function CardA({ reward, theme }: { reward: Reward; theme: Theme }) {
  const state = ringState(reward)
  const card = bestCardFor(reward.mcc)
  return (
    <div className="flex gap-3 rounded-2xl border border-[#e0dcc8] bg-white p-4 shadow-[4px_5px_0_#e6e2ce] transition hover:-translate-y-0.5">
      <ExpiryRing state={state} theme={theme} size={46}>
        <Monogram name={reward.merchant_name} theme={theme} size={30} />
      </ExpiryRing>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate font-semibold text-[#1f3029]">{reward.merchant_name}</span>
          {needsReview(reward) ? (
            <span className="rounded-full bg-[#f3e7cf] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#8a5a2d]">
              review · {Math.round((reward.overall_confidence ?? 0) * 100)}%
            </span>
          ) : null}
        </div>
        <div className="font-serif text-lg leading-tight text-[#174b34]">{formatRewardValue(reward)}</div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-[#6b7f72]">
          <span className={state.urgency === 'soon' ? 'font-semibold text-[#C2452D]' : ''}>
            {formatExpiry(reward.expires_at, NOW)}
          </span>
          {card ? (
            <span className="rounded-full bg-[#edf3e8] px-1.5 py-0.5 text-[#174b34]">
              {card.issuer} {card.name} · {card.rate}%
            </span>
          ) : null}
          <span>{SOURCE_LABEL[reward.source] ?? reward.source}</span>
        </div>
      </div>
    </div>
  )
}

function DashboardA({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useDashboardModel(data)
  return (
    <div className="min-h-screen bg-[#f8f8ef] text-[#1f3029] mock-grain" style={{ fontFamily: 'Inter, sans-serif' }}>
      <header className="border-b border-[#e0dcc8]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <ExpiryRing state={{ fraction: 0.72, daysLeft: null, urgency: 'later' }} theme={theme} size={26} stroke={3} />
            <span className="font-serif text-2xl tracking-tight text-[#174b34]">Lapse</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-[#52705d]">
            <span className="font-medium text-[#174b34]">Rewards</span>
            <span>Savings</span>
            <span>Calendar</span>
            <span className="rounded-full border border-[#e0dcc8] bg-white px-3 py-1">{DEMO_USER.email}</span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="font-serif text-4xl tracking-tight">Good afternoon, Aamir.</h1>
        <p className="mt-1 text-sm text-[#52705d]">
          {m.wallet.active_rewards_count} rewards in your pocket · {m.wallet.expiring_soon_count} lapse within 3 days
        </p>

        <div className="mt-5 flex items-center gap-3 rounded-2xl border border-[#e8d7ad] bg-[#f3e7cf] px-4 py-3">
          <ExpiryRing state={{ fraction: 0.18, daysLeft: 1, urgency: 'soon' }} theme={theme} size={34} stroke={4}>
            <span className="text-[10px] font-bold text-[#C2452D]">1d</span>
          </ExpiryRing>
          <p className="text-sm">
            <span className="font-semibold">Use it before it lapses —</span>{' '}
            {m.nudges
              .slice(0, 3)
              .map((r) => `${r.merchant_name} ${formatRewardValue(r)}`)
              .join(', ')}{' '}
            and {m.nudges.length - 3} more lapse within 3 days.
          </p>
        </div>

        <div className="mt-8 grid grid-cols-[minmax(0,1fr)_320px] items-start gap-8">
          <section className="space-y-8">
            {BUCKETS.map((bucket) => {
              const list = m.groups[bucket]
              if (!list.length) return null
              return (
                <div key={bucket}>
                  <div className="mb-3 flex items-baseline gap-3">
                    <h2 className="font-serif text-2xl">{bucket}</h2>
                    <span className="text-xs uppercase tracking-[0.18em] text-[#8fa394]">{list.length} rewards</span>
                    <div className="flex-1 border-b border-dashed border-[#d7d2bd]" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {list.slice(0, bucket === 'Misc' ? 4 : 6).map((reward) => (
                      <CardA key={reward.id} reward={reward} theme={theme} />
                    ))}
                  </div>
                </div>
              )
            })}
          </section>

          <aside className="space-y-4">
            <section className="rounded-2xl bg-[#174b34] p-5 text-[#f8f8ef] shadow-[6px_7px_0_#cfe0c7]">
              <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#b7d0b2]">Saved with Lapse</h2>
              <p className="mt-2 font-serif text-5xl tracking-tight">{formatDollars(data.savings.total)}</p>
              <div className="mt-2 h-14">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={m.series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                    <Area type="monotone" dataKey="cumulative" stroke="#b7d0b2" fill="#2e6a42" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-1 text-xs text-[#b7d0b2]">
                {data.savings.items.length} rewards used since Sep 8 → view savings
              </p>
            </section>

            <section className="rounded-2xl border border-[#e0dcc8] bg-white p-5 shadow-[4px_5px_0_#e6e2ce]">
              <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8fa394]">Lapsing next</h2>
              <ul className="mt-3 space-y-3">
                {m.nudges.slice(0, 5).map((reward) => {
                  const state = ringState(reward)
                  return (
                    <li key={reward.id} className="flex items-center gap-3">
                      <ExpiryRing state={state} theme={theme} size={34} stroke={3}>
                        <RingDays state={state} className="text-[9px] font-bold text-[#C2452D]" />
                      </ExpiryRing>
                      <div className="min-w-0 text-sm">
                        <div className="truncate font-semibold">{reward.merchant_name}</div>
                        <div className="text-xs text-[#6b7f72]">
                          {formatRewardValue(reward)} · {formatExpiry(reward.expires_at, NOW)}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>

            <section className="rounded-2xl border border-[#e0dcc8] bg-white p-5 shadow-[4px_5px_0_#e6e2ce]">
              <h2 className="text-xs font-semibold uppercase tracking-[0.18em] text-[#8fa394]">Where you save</h2>
              <ul className="mt-3 space-y-2">
                {m.history.slice(0, 4).map((h) => (
                  <li key={h.merchant} className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Monogram name={h.merchant} theme={theme} size={24} />
                      {h.merchant}
                    </span>
                    <span className="font-serif text-[#174b34]">{centsToDollars(h.totalCents)}</span>
                  </li>
                ))}
              </ul>
            </section>
          </aside>
        </div>
      </main>
    </div>
  )
}

/* ================================================================== */
/* B — Clip & Save                                                     */
/* ================================================================== */

function CouponB({ reward, theme }: { reward: Reward; theme: Theme }) {
  const state = ringState(reward)
  const card = bestCardFor(reward.mcc)
  const urgent = state.urgency === 'soon'
  return (
    <div className="relative border-2 border-[#141414] bg-white" style={{ boxShadow: '5px 5px 0 #141414' }}>
      {urgent ? (
        <span
          className="absolute -right-2 -top-3 z-10 rotate-6 border-2 border-[#141414] bg-[#FF5C1C] px-2 py-0.5 text-[10px] font-black uppercase text-white"
          style={{ fontFamily: 'Archivo, sans-serif' }}
        >
          {state.daysLeft === 0 ? 'today!' : state.daysLeft === 1 ? 'tomorrow!' : `${state.daysLeft} days!`}
        </span>
      ) : null}
      <div className="flex items-center gap-2 border-b-2 border-dashed border-[#141414] px-3 py-2">
        <Monogram name={reward.merchant_name} theme={theme} size={30} />
        <span className="truncate text-sm font-bold uppercase">{reward.merchant_name}</span>
        <ExpiryRing state={state} theme={theme} size={26} stroke={4} />
      </div>
      <div className="px-3 py-2">
        <div className="text-2xl font-black leading-none" style={{ fontFamily: 'Archivo, sans-serif' }}>
          {formatRewardValue(reward)}
        </div>
        <div className="mt-1 text-[11px] font-semibold text-[#5a5a5a]">
          {formatExpiry(reward.expires_at, NOW)}
          {reward.min_spend ? ` · min $${Number(reward.min_spend)}` : ''}
        </div>
        {card ? (
          <div className="mt-1 inline-block bg-[#BCE740] px-1.5 py-0.5 text-[10px] font-bold uppercase">
            pay w/ {card.issuer} {card.name} +{card.rate}%
          </div>
        ) : null}
      </div>
      {reward.code ? (
        <div className="flex items-center justify-between gap-2 border-t-2 border-[#141414] bg-[#FFF6E9] px-3 py-1.5">
          <span className="mock-barcode h-5 w-16" />
          <span className="text-xs font-black tracking-widest">{reward.code}</span>
        </div>
      ) : null}
    </div>
  )
}

function DashboardB({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useDashboardModel(data)
  const ticker = m.nudges.map((r) => `${r.merchant_name.toUpperCase()} ${formatRewardValue(r)} — ${formatExpiry(r.expires_at, NOW).toUpperCase()}`).join('  ✂  ')
  return (
    <div className="min-h-screen bg-[#FFF6E9] text-[#141414]" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <div className="overflow-hidden whitespace-nowrap border-b-2 border-[#141414] bg-[#141414] py-1.5 text-xs font-bold tracking-wider text-[#BCE740]">
        <div className="mock-marquee inline-block">{ticker}  ✂  {ticker}</div>
      </div>

      <header className="border-b-2 border-[#141414] bg-[#FF5C1C]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <ExpiryRing state={{ fraction: 0.65, daysLeft: null, urgency: 'none' }} theme={theme} size={30} stroke={5} />
            <span className="text-3xl font-black uppercase tracking-tight text-white" style={{ fontFamily: 'Archivo, sans-serif' }}>
              Lapse
            </span>
          </div>
          <nav className="flex items-center gap-2 text-xs font-black uppercase">
            {['Rewards', 'Savings', 'Calendar'].map((item, i) => (
              <span key={item} className={`border-2 border-[#141414] px-3 py-1 ${i === 0 ? 'bg-[#141414] text-[#BCE740]' : 'bg-white'}`}>
                {item}
              </span>
            ))}
            <span className="border-2 border-[#141414] bg-[#CBA6FF] px-3 py-1">{DEMO_USER.email}</span>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Saved so far', value: formatDollars(data.savings.total), bg: '#BCE740' },
            { label: 'Rewards clipped', value: String(m.wallet.active_rewards_count), bg: '#fff' },
            { label: 'Lapse in 3 days', value: String(m.wallet.expiring_soon_count), bg: '#FF5C1C' },
            { label: 'Used this fall', value: String(data.savings.items.length), bg: '#74C0FF' },
          ].map((stat) => (
            <div key={stat.label} className="border-2 border-[#141414] px-4 py-3" style={{ background: stat.bg, boxShadow: '6px 6px 0 #141414' }}>
              <div className="text-[11px] font-black uppercase tracking-wider">{stat.label}</div>
              <div className="text-4xl font-black leading-tight" style={{ fontFamily: 'Archivo, sans-serif' }}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex rotate-[-0.4deg] items-center gap-3 border-2 border-[#141414] bg-[#F5A800] px-4 py-2" style={{ boxShadow: '6px 6px 0 #141414' }}>
          <span className="text-xl">✂</span>
          <p className="text-sm font-bold uppercase">
            Clip 'em before they lapse: {m.nudges.length} coupons die within 3 days — {formatRewardValue(m.nudges[0])} at {m.nudges[0].merchant_name} among them
          </p>
        </div>

        {BUCKETS.map((bucket) => {
          const list = m.groups[bucket]
          if (!list.length) return null
          return (
            <section key={bucket} className="mt-7">
              <h2 className="mb-3 inline-block -rotate-1 border-2 border-[#141414] bg-white px-3 py-1 text-xl font-black uppercase" style={{ fontFamily: 'Archivo, sans-serif', boxShadow: '4px 4px 0 #141414' }}>
                {bucket} · {list.length}
              </h2>
              <div className="grid grid-cols-3 gap-4">
                {list.slice(0, bucket === 'Misc' ? 3 : 6).map((reward) => (
                  <CouponB key={reward.id} reward={reward} theme={theme} />
                ))}
              </div>
            </section>
          )
        })}

        <section className="mt-8 border-2 border-[#141414] bg-white p-4" style={{ boxShadow: '6px 6px 0 #141414' }}>
          <h2 className="text-sm font-black uppercase tracking-wider">Your receipts</h2>
          <div className="mt-2 flex flex-wrap gap-2">
            {m.history.map((h) => (
              <span key={h.merchant} className="border-2 border-[#141414] bg-[#FFF6E9] px-2 py-1 text-xs font-bold">
                {h.merchant} · {h.count}× · {centsToDollars(h.totalCents)}
              </span>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

/* ================================================================== */
/* C — Night Vault                                                     */
/* ================================================================== */

function RowC({ reward, theme }: { reward: Reward; theme: Theme }) {
  const state = ringState(reward)
  const card = bestCardFor(reward.mcc)
  const urgentText = state.urgency === 'soon' ? 'text-[#FF7088]' : state.urgency === 'week' ? 'text-[#FFC24B]' : 'text-[#6FA08A]'
  return (
    <div className="grid grid-cols-[44px_1.4fr_1fr_1.2fr_0.8fr_0.9fr] items-center gap-3 border-b border-[#1D3127] px-4 py-2.5 text-sm hover:bg-[#122019]">
      <ExpiryRing state={state} theme={theme} size={36} stroke={3}>
        <RingDays state={state} className={`font-mono text-[9px] font-bold ${urgentText}`} />
      </ExpiryRing>
      <div className="flex min-w-0 items-center gap-2.5">
        <Monogram name={reward.merchant_name} theme={theme} size={28} />
        <div className="min-w-0">
          <div className="truncate font-medium text-[#E7F4EC]">{reward.merchant_name}</div>
          <div className="truncate text-[10px] uppercase tracking-wider text-[#4E6E5D]">{SOURCE_LABEL[reward.source] ?? reward.source}</div>
        </div>
      </div>
      <div className="font-mono text-[#3DDC97]">{formatRewardValue(reward)}</div>
      <div className="truncate text-xs text-[#9DBCA9]">
        {card ? `${card.issuer} ${card.name} · ${card.rate}%` : '—'}
      </div>
      <div className="font-mono text-xs">
        {needsReview(reward) ? (
          <span className="rounded border border-[#FFC24B]/40 bg-[#FFC24B]/10 px-1.5 py-0.5 text-[#FFC24B]">
            {Math.round((reward.overall_confidence ?? 0) * 100)}%
          </span>
        ) : (
          <span className="text-[#4E6E5D]">{Math.round((reward.overall_confidence ?? 0) * 100)}%</span>
        )}
      </div>
      <div className={`text-right font-mono text-xs ${urgentText}`}>{formatExpiry(reward.expires_at, NOW)}</div>
    </div>
  )
}

function DashboardC({ data, theme }: { data: MockupData; theme: Theme }) {
  const m = useDashboardModel(data)
  const all = [...m.groups.Food, ...m.groups.Clothing, ...m.groups.Misc]
    .sort((a, b) => (a.expires_at ?? '9999').localeCompare(b.expires_at ?? '9999'))
  return (
    <div className="flex min-h-screen bg-[#0A1310] text-[#E7F4EC] mock-scanlines" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <aside className="flex w-48 shrink-0 flex-col border-r border-[#1D3127] px-4 py-5">
        <div className="flex items-center gap-2">
          <ExpiryRing state={{ fraction: 0.72, daysLeft: null, urgency: 'later' }} theme={theme} size={28} stroke={4} />
          <span className="text-xl font-semibold tracking-tight text-[#3DDC97]">Lapse</span>
        </div>
        <nav className="mt-8 space-y-1 text-sm">
          {['Rewards', 'Savings', 'Calendar', 'Wallet'].map((item, i) => (
            <div key={item} className={`rounded-lg px-3 py-2 ${i === 0 ? 'bg-[#16261E] text-[#3DDC97]' : 'text-[#9DBCA9]'}`}>
              {item}
            </div>
          ))}
        </nav>
        <div className="mt-auto rounded-lg border border-[#1D3127] bg-[#122019] p-3 text-[11px] text-[#9DBCA9]">
          <div className="font-mono text-[#3DDC97]">{DEMO_USER.email}</div>
          forwarding live · {m.wallet.cards.length} Visa cards linked
        </div>
      </aside>

      <main className="min-w-0 flex-1 px-7 py-6">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Reward vault</h1>
            <p className="mt-1 font-mono text-xs text-[#6FA08A]">
              SYNCED {NOW.toISOString().slice(0, 16).replace('T', ' ')}Z · {m.wallet.active_rewards_count} ACTIVE · {m.wallet.expiring_soon_count} CRITICAL
            </p>
          </div>
          <div className="flex gap-6 text-right">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Saved to date</div>
              <div className="font-mono text-3xl font-bold text-[#3DDC97]" style={{ textShadow: '0 0 18px rgba(61,220,151,0.45)' }}>
                {formatDollars(data.savings.total)}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">At risk ≤3d</div>
              <div className="font-mono text-3xl font-bold text-[#FF7088]">{m.nudges.length}</div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3 rounded-xl border border-[#FFC24B]/30 bg-[#FFC24B]/10 px-4 py-2.5 text-sm text-[#FFC24B]">
          <span className="font-mono text-xs font-bold">LAPSE ALERT</span>
          {m.nudges.slice(0, 3).map((r) => `${r.merchant_name} ${formatRewardValue(r)} (${formatExpiry(r.expires_at, NOW).toLowerCase()})`).join(' · ')} +{m.nudges.length - 3} more
        </div>

        <div className="mt-5 overflow-hidden rounded-xl border border-[#1D3127] bg-[#0E1A14]">
          <div className="grid grid-cols-[44px_1.4fr_1fr_1.2fr_0.8fr_0.9fr] gap-3 border-b border-[#1D3127] bg-[#122019] px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">
            <span>⏱</span><span>Merchant / source</span><span>Value</span><span>Best card</span><span>Conf.</span><span className="text-right">Expiry</span>
          </div>
          {all.slice(0, 9).map((reward) => (
            <RowC key={reward.id} reward={reward} theme={theme} />
          ))}
        </div>
      </main>

      <aside className="w-72 shrink-0 space-y-4 border-l border-[#1D3127] px-5 py-6">
        <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
          <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Savings trajectory</h2>
          <div className="mt-2 h-20">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={m.series} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="glowC" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3DDC97" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#3DDC97" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area type="monotone" dataKey="cumulative" stroke="#3DDC97" strokeWidth={2} fill="url(#glowC)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 font-mono text-[11px] text-[#9DBCA9]">
            {data.savings.items.length} redemptions · since 2026-09-08
          </p>
        </section>

        <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
          <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Critical queue</h2>
          <ul className="mt-2 space-y-2.5">
            {m.nudges.slice(0, 5).map((reward) => {
              const state = ringState(reward)
              return (
                <li key={reward.id} className="flex items-center gap-2.5 text-sm">
                  <ExpiryRing state={state} theme={theme} size={30} stroke={3}>
                    <RingDays state={state} className="font-mono text-[8px] font-bold text-[#FF7088]" />
                  </ExpiryRing>
                  <div className="min-w-0">
                    <div className="truncate text-[#E7F4EC]">{reward.merchant_name}</div>
                    <div className="font-mono text-[10px] text-[#6FA08A]">{formatRewardValue(reward)} · {reward.code ?? 'auto'}</div>
                  </div>
                </li>
              )
            })}
          </ul>
        </section>

        <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-4">
          <h2 className="font-mono text-[10px] uppercase tracking-widest text-[#6FA08A]">Merchant ledger</h2>
          <ul className="mt-2 space-y-1.5 font-mono text-xs">
            {m.history.slice(0, 5).map((h) => (
              <li key={h.merchant} className="flex justify-between">
                <span className="text-[#9DBCA9]">{h.merchant}</span>
                <span className="text-[#3DDC97]">{centsToDollars(h.totalCents)}</span>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}

export function MockDashboard({ theme }: { theme: Theme }) {
  const data = useMockupData()
  if (!data) return null
  if (theme.id === 'b') return <DashboardB data={data} theme={theme} />
  if (theme.id === 'c') return <DashboardC data={data} theme={theme} />
  return <DashboardA data={data} theme={theme} />
}
