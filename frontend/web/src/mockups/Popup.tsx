import { formatDollars } from '../util/money'
import { formatExpiry, formatRewardValue } from '../util/rewards'
import { DEMO_USER } from '../util/demo'
import { hollisterPopup, NOW, ringState } from './data'
import { ExpiryRing, RingDays } from './Ring'
import type { Theme } from './themes'

const data = hollisterPopup()

function Toast({ theme }: { theme: Theme }) {
  const text = `New reward added · ${data.toast.merchant} ${data.toast.label} · ${data.toast.code}`
  if (theme.id === 'b') {
    return (
      <div className="rotate-[-0.5deg] border-2 border-[#141414] bg-[#BCE740] px-3 py-1.5 text-[11px] font-black uppercase" style={{ boxShadow: '4px 4px 0 #141414' }}>
        ✉ {text}
      </div>
    )
  }
  if (theme.id === 'c') {
    return (
      <div className="rounded-lg border border-[#3DDC97]/40 bg-[#3DDC97]/10 px-3 py-1.5 font-mono text-[11px] text-[#3DDC97]">
        ⚡ {text}
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-[#cfe0c7] bg-[#edf3e8] px-3 py-1.5 text-[11px] font-medium text-[#174b34]">
      ✉ {text}
    </div>
  )
}

/* Shared, theme-styled breakdown rows: the at-checkout savings preview. */
function Breakdown({ rows }: { rows: { cls: string; label: string; value: string }[] }) {
  return (
    <div className="space-y-1">
      {rows.map((row) => (
        <div key={row.label} className={`flex items-center justify-between text-xs ${row.cls}`}>
          <span>{row.label}</span>
          <span>{row.value}</span>
        </div>
      ))}
    </div>
  )
}

function PopupA({ theme }: { theme: Theme }) {
  const state = ringState(data.reward)
  return (
    <div className="flex w-[400px] flex-col gap-3 bg-[#f8f8ef] p-4 text-[#1f3029] mock-grain" style={{ fontFamily: 'Inter, sans-serif' }}>
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ExpiryRing state={{ fraction: 0.72, daysLeft: null, urgency: 'later' }} theme={theme} size={24} stroke={3} />
          <span className="font-serif text-xl text-[#174b34]">Lapse</span>
        </div>
        <span className="text-[10px] text-[#8fa394]">{DEMO_USER.email}</span>
      </header>
      <Toast theme={theme} />
      <section className="flex items-center gap-3 rounded-2xl border border-[#e0dcc8] bg-white px-3 py-2.5 shadow-[3px_4px_0_#e6e2ce]">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-[#174b34] font-serif text-white">H</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{data.merchant.name}</span>
            <span className="rounded-full bg-[#f3e7cf] px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-[#8a5a2d]">cart · {data.items.length} items</span>
          </div>
          <div className="text-[11px] text-[#6b7f72]">{data.merchant.domain} · {data.merchant.category}</div>
        </div>
      </section>
      <section className="flex gap-3 rounded-2xl border border-[#e0dcc8] bg-white p-3 shadow-[3px_4px_0_#e6e2ce]">
        <ExpiryRing state={state} theme={theme} size={42}>
          <RingDays state={state} className="text-[9px] font-bold text-[#C2452D]" />
        </ExpiryRing>
        <div className="min-w-0 flex-1">
          <div className="font-serif text-lg leading-tight text-[#174b34]">{formatRewardValue(data.reward)} · {data.reward.code}</div>
          <div className="text-[11px] text-[#6b7f72]">
            {formatExpiry(data.reward.expires_at, NOW)} · min ${Number(data.reward.min_spend)} · excludes {data.reward.exclusions?.join(', ').toLowerCase()}
          </div>
        </div>
        <button className="self-center rounded-full bg-[#174b34] px-3 py-1 text-xs font-semibold text-white">Copy</button>
      </section>
      <section className="rounded-2xl bg-[#174b34] p-4 text-[#f8f8ef] shadow-[4px_5px_0_#cfe0c7]">
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-[#b7d0b2]">You'll pay</div>
            <div className="text-xs text-[#8aa98b] line-through">{formatDollars(data.originalPrice)}</div>
            <div className="font-serif text-4xl tracking-tight">{formatDollars(data.finalPrice)}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[#b7d0b2]">You keep</div>
            <div className="font-serif text-2xl">{formatDollars(data.totalSavings)}</div>
            <div className="text-[11px] text-[#b7d0b2]">{Number(data.savingsPercent).toFixed(1)}% of the cart</div>
          </div>
        </div>
        <div className="mt-3 border-t border-[#2e6a42] pt-2">
          <Breakdown
            rows={[
              { cls: 'text-[#d9e8d1]', label: `Code ${data.reward.code} (${formatRewardValue(data.reward)})`, value: `−${formatDollars(data.rewardSavings)}` },
              { cls: 'text-[#d9e8d1]', label: `${data.card.issuer} ${data.card.name} · ${data.card.rate}% on ${data.card.category}`, value: `+${formatDollars(data.cardCashback)} back` },
            ]}
          />
        </div>
        <button className="mt-3 w-full rounded-xl bg-[#f8f8ef] py-2 text-sm font-semibold text-[#174b34]">Apply HCOFALL10 & mark used</button>
      </section>
      <p className="text-center text-[10px] text-[#8fa394]">Open dashboard</p>
    </div>
  )
}

function PopupB({ theme }: { theme: Theme }) {
  const state = ringState(data.reward)
  return (
    <div className="flex w-[400px] flex-col gap-3 bg-[#FFF6E9] p-4 text-[#141414]" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <header className="flex items-center justify-between border-2 border-[#141414] bg-[#FF5C1C] px-3 py-1.5" style={{ boxShadow: '4px 4px 0 #141414' }}>
        <span className="text-xl font-black uppercase text-white" style={{ fontFamily: 'Archivo, sans-serif' }}>Lapse</span>
        <span className="bg-[#141414] px-2 py-0.5 text-[9px] font-bold uppercase text-[#BCE740]">on {data.merchant.domain}</span>
      </header>
      <Toast theme={theme} />
      <section className="border-2 border-[#141414] bg-white" style={{ boxShadow: '5px 5px 0 #141414' }}>
        <div className="flex items-center gap-2 border-b-2 border-dashed border-[#141414] px-3 py-2">
          <div className="grid h-8 w-8 place-items-center border-2 border-[#141414] bg-[#74C0FF] font-black">H</div>
          <span className="text-sm font-black uppercase">{data.merchant.name}</span>
          <span className="rotate-2 border-2 border-[#141414] bg-[#F5A800] px-1.5 text-[9px] font-black uppercase">cart $500</span>
          <ExpiryRing state={state} theme={theme} size={26} stroke={4} />
        </div>
        <div className="px-3 py-2">
          <div className="text-2xl font-black" style={{ fontFamily: 'Archivo, sans-serif' }}>{formatRewardValue(data.reward)}</div>
          <div className="text-[11px] font-semibold text-[#5a5a5a]">
            {formatExpiry(data.reward.expires_at, NOW)} · min ${Number(data.reward.min_spend)} · no gift cards / clearance
          </div>
        </div>
        <div className="flex items-center justify-between border-t-2 border-[#141414] bg-[#FFF6E9] px-3 py-1.5">
          <span className="mock-barcode h-5 w-20" />
          <span className="text-sm font-black tracking-[0.2em]">{data.reward.code}</span>
          <span className="border-2 border-[#141414] bg-[#BCE740] px-2 py-0.5 text-[10px] font-black uppercase">copy</span>
        </div>
      </section>
      <section className="border-2 border-[#141414] bg-[#141414] p-3 text-white" style={{ boxShadow: '5px 5px 0 #FF5C1C' }}>
        <div className="flex items-end justify-between">
          <div>
            <div className="text-[9px] font-black uppercase tracking-widest text-[#BCE740]">You pay</div>
            <div className="text-[11px] text-white/50 line-through">{formatDollars(data.originalPrice)}</div>
            <div className="text-4xl font-black text-[#BCE740]" style={{ fontFamily: 'Archivo, sans-serif' }}>{formatDollars(data.finalPrice)}</div>
          </div>
          <div className="rotate-3 border-2 border-[#BCE740] px-2 py-1 text-center">
            <div className="text-[9px] font-black uppercase">saved</div>
            <div className="text-xl font-black text-[#BCE740]">{formatDollars(data.totalSavings)}</div>
            <div className="text-[9px] font-bold">{Number(data.savingsPercent).toFixed(1)}%</div>
          </div>
        </div>
        <div className="mt-2 border-t-2 border-dashed border-white/30 pt-2">
          <Breakdown
            rows={[
              { cls: 'font-bold text-white', label: `✂ ${data.reward.code} — ${formatRewardValue(data.reward)}`, value: `−${formatDollars(data.rewardSavings)}` },
              { cls: 'font-bold text-[#74C0FF]', label: `💳 ${data.card.issuer} ${data.card.name} ${data.card.rate}%`, value: `+${formatDollars(data.cardCashback)}` },
            ]}
          />
        </div>
        <button className="mt-3 w-full border-2 border-[#BCE740] bg-[#BCE740] py-2 text-sm font-black uppercase text-[#141414]">Stack it → pay $450.00</button>
      </section>
      <p className="text-center text-[10px] font-bold uppercase text-[#5a5a5a]">{DEMO_USER.email} · open dashboard</p>
    </div>
  )
}

function PopupC({ theme }: { theme: Theme }) {
  const state = ringState(data.reward)
  return (
    <div className="flex w-[400px] flex-col gap-3 bg-[#0A1310] p-4 text-[#E7F4EC] mock-scanlines" style={{ fontFamily: '"Space Grotesk", sans-serif' }}>
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ExpiryRing state={{ fraction: 0.72, daysLeft: null, urgency: 'later' }} theme={theme} size={24} stroke={3} />
          <span className="text-lg font-semibold text-[#3DDC97]">Lapse</span>
        </div>
        <span className="font-mono text-[10px] text-[#6FA08A]">{data.merchant.domain} · CART</span>
      </header>
      <Toast theme={theme} />
      <section className="rounded-xl border border-[#1D3127] bg-[#0E1A14] p-3">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg border border-[#2A4335] bg-[#16261E] font-semibold text-[#3DDC97]">H</div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {data.merchant.name}
              <span className="rounded border border-[#FFC24B]/40 bg-[#FFC24B]/10 px-1.5 py-0.5 font-mono text-[9px] uppercase text-[#FFC24B]">checkout detected</span>
            </div>
            <div className="font-mono text-[10px] text-[#6FA08A]">MCC {data.merchant.mcc} · {data.merchant.category}</div>
          </div>
        </div>
        <div className="mt-2.5 flex gap-3 rounded-lg border border-[#1D3127] bg-[#122019] p-2.5">
          <ExpiryRing state={state} theme={theme} size={38}>
            <RingDays state={state} className="font-mono text-[9px] font-bold text-[#FFC24B]" />
          </ExpiryRing>
          <div className="min-w-0 flex-1">
            <div className="font-mono text-sm text-[#3DDC97]">{formatRewardValue(data.reward)} · {data.reward.code}</div>
            <div className="font-mono text-[10px] text-[#6FA08A]">{formatExpiry(data.reward.expires_at, NOW).toUpperCase()} · MIN ${Number(data.reward.min_spend)} · CONF {Math.round((data.reward.overall_confidence ?? 0) * 100)}%</div>
          </div>
        </div>
      </section>
      <section className="rounded-xl border border-[#3DDC97]/40 bg-[#0E1A14] p-3.5" style={{ boxShadow: '0 0 28px rgba(61,220,151,0.15) inset' }}>
        <div className="flex items-end justify-between">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-widest text-[#6FA08A]">Final price</div>
            <div className="font-mono text-xs text-[#4E6E5D] line-through">{formatDollars(data.originalPrice)}</div>
            <div className="font-mono text-4xl font-bold text-[#3DDC97]" style={{ textShadow: '0 0 18px rgba(61,220,151,0.5)' }}>{formatDollars(data.finalPrice)}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[9px] uppercase tracking-widest text-[#6FA08A]">Total savings</div>
            <div className="font-mono text-xl font-bold text-[#FFC24B]">{formatDollars(data.totalSavings)}</div>
            <div className="font-mono text-[10px] text-[#9DBCA9]">{Number(data.savingsPercent).toFixed(1)}% · solver optimal</div>
          </div>
        </div>
        <div className="mt-2.5 space-y-1 border-t border-[#1D3127] pt-2 font-mono">
          <Breakdown
            rows={[
              { cls: 'text-[#9DBCA9]', label: `01 · ${data.reward.code} (${formatRewardValue(data.reward)})`, value: `−${formatDollars(data.rewardSavings)}` },
              { cls: 'text-[#9DBCA9]', label: `02 · ${data.card.issuer} ${data.card.name} @ ${data.card.rate}%`, value: `+${formatDollars(data.cardCashback)}` },
            ]}
          />
        </div>
        <button className="mt-3 w-full rounded-lg bg-[#3DDC97] py-2 font-mono text-sm font-bold uppercase text-[#0A1310]">Apply stack</button>
      </section>
      <p className="text-center font-mono text-[9px] uppercase tracking-widest text-[#4E6E5D]">{DEMO_USER.email} · open dashboard</p>
    </div>
  )
}

export function MockPopup({ theme }: { theme: Theme }) {
  const inner = theme.id === 'b' ? <PopupB theme={theme} /> : theme.id === 'c' ? <PopupC theme={theme} /> : <PopupA theme={theme} />
  return <div className="grid min-h-screen place-items-start bg-[#3b3b3b] [&>*]:shadow-2xl">{inner}</div>
}
