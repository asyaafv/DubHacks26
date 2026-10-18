import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExpiryRing, expiryFraction } from '../components/ExpiryRing'
import { RewardDrawer } from '../components/RewardDrawer'
import { SidePanel } from '../components/SidePanel'
import { useRewards } from '../context/RewardsContext'
import type { Membership, Reward } from '../types'
import {
  addDays,
  dateKey,
  formatDate,
  localDay,
  monthGrid,
  sameDay,
  startOfDay,
  weekdayLabels,
  weekDays,
} from '../util/dates'
import { expiryUrgency, formatRewardValue, isOpenReward } from '../util/rewards'

type Mode = 'week' | 'month'

export function CalendarPage() {
  const { rewards, wallet, loading, redeem } = useRewards()
  const [mode, setMode] = useState<Mode>('week')
  const [cursor, setCursor] = useState<Date | null>(null)
  const [rewardsOnly, setRewardsOnly] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [membership, setMembership] = useState<Membership | null>(null)

  const openRewards = useMemo(() => rewards.filter((reward) => isOpenReward(reward) && reward.expires_at), [rewards])

  useEffect(() => {
    if (cursor || openRewards.length === 0) return
    const today = startOfDay(new Date())
    const upcoming = openRewards
      .map((reward) => new Date(reward.expires_at as string))
      .filter((date) => startOfDay(date) >= today)
      .sort((a, b) => a.getTime() - b.getTime())
    setCursor(upcoming[0] ?? today)
  }, [cursor, openRewards])

  const anchor = cursor ?? new Date()
  const days = mode === 'week' ? weekDays(anchor) : monthGrid(anchor)
  const memberships = rewardsOnly ? [] : (wallet?.memberships ?? []).filter((item) => item.expires_at)

  const selected = rewards.find((reward) => reward.id === selectedId) ?? null

  function shift(direction: -1 | 1) {
    setCursor((current) => {
      const base = current ?? new Date()
      if (mode === 'week') return addDays(base, direction * 7)
      return new Date(base.getFullYear(), base.getMonth() + direction, 1)
    })
  }

  const rangeLabel =
    mode === 'week'
      ? `${days[0].toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${days[6].toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`
      : anchor.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

  async function handleRedeem(saved: string) {
    if (!selected) return
    await redeem(selected.id, saved)
    setSelectedId(null)
  }

  return (
    <div>
      <Link
        to="/dashboard"
        className="inline-block border-2 border-line bg-white px-3 py-1 text-xs font-black uppercase text-ink shadow-card"
      >
        ← Back
      </Link>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-4xl font-black uppercase tracking-tight text-ink">Calendar</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={mode === 'week'}
            onClick={() => setMode('week')}
            className={`border-2 border-line px-3 py-1.5 text-xs font-black uppercase ${mode === 'week' ? 'bg-ink text-lime' : 'bg-white text-ink'}`}
          >
            Week
          </button>
          <button
            type="button"
            aria-pressed={mode === 'month'}
            onClick={() => setMode('month')}
            className={`border-2 border-line px-3 py-1.5 text-xs font-black uppercase ${mode === 'month' ? 'bg-ink text-lime' : 'bg-white text-ink'}`}
          >
            Month
          </button>
        </div>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => shift(-1)}
            className="border-2 border-line bg-white px-3 py-1.5 text-sm font-black shadow-card"
            aria-label={mode === 'week' ? 'Previous week' : 'Previous month'}
          >
            ←
          </button>
          <p className="min-w-48 text-center font-display text-base font-black uppercase text-ink">{rangeLabel}</p>
          <button
            type="button"
            onClick={() => shift(1)}
            className="border-2 border-line bg-white px-3 py-1.5 text-sm font-black shadow-card"
            aria-label={mode === 'week' ? 'Next week' : 'Next month'}
          >
            →
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm font-bold text-ink">
          <input
            type="checkbox"
            checked={rewardsOnly}
            onChange={(event) => setRewardsOnly(event.target.checked)}
          />
          Rewards only
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-4 text-xs font-bold uppercase text-muted">
        <Legend swatch="bg-tangerine" label="Next 2 days" />
        <Legend swatch="bg-amber" label="This week" />
        <Legend swatch="bg-ink" label="Later" />
      </div>

      {loading ? <p className="mt-6 text-sm font-bold text-muted">Loading rewards…</p> : null}

      <div className="mt-4 grid grid-cols-7 gap-2">
        {weekdayLabels().map((label) => (
          <div key={label} className="px-1 font-display text-xs font-black uppercase tracking-wide text-ink">
            {label}
          </div>
        ))}
        {days.map((day) => {
          const key = dateKey(day)
          const inMonth = day.getMonth() === anchor.getMonth()
          const dayRewards = openRewards.filter((reward) => localDay(reward.expires_at as string) === key)
          const dayMemberships = memberships.filter((item) => item.expires_at && localDay(item.expires_at) === key)
          const today = sameDay(day, new Date())
          return (
            <div
              key={key}
              className={`border-2 border-line p-2 shadow-card ${today ? 'bg-lime' : 'bg-white'} ${
                mode === 'week' ? 'min-h-48' : 'min-h-28'
              } ${mode === 'month' && !inMonth ? 'opacity-50' : ''}`}
            >
              <div className={`font-display text-sm font-black ${today ? 'text-ink' : 'text-ink'}`}>{day.getDate()}</div>
              <div className="mt-2 flex flex-col gap-1">
                {dayRewards.map((reward) => (
                  <RewardChip key={reward.id} reward={reward} compact={mode === 'month'} onClick={() => {
                    setMembership(null)
                    setSelectedId(reward.id)
                  }} />
                ))}
                {dayMemberships.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSelectedId(null)
                      setMembership(item)
                    }}
                    className="truncate border-2 border-line bg-lilac px-1.5 py-1 text-left text-[11px] font-bold text-ink"
                  >
                    {item.merchant_name} membership
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {selected ? (
        <RewardDrawer key={selected.id} reward={selected} onClose={() => setSelectedId(null)} onRedeem={handleRedeem} />
      ) : null}
      {membership ? (
        <SidePanel title="More details" onClose={() => setMembership(null)}>
          <h3 className="font-display text-xl font-black uppercase text-ink">{membership.merchant_name}</h3>
          <p className="mt-1 font-bold text-tangerine">{membership.program_name}</p>
          {membership.tier ? <p className="mt-1 text-sm font-semibold text-muted">{membership.tier}</p> : null}
          <p className="mt-4 text-sm font-semibold text-muted">Expires {formatDate(membership.expires_at)}</p>
          {membership.benefits && membership.benefits.length > 0 ? (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted">
              {membership.benefits.map((benefit) => (
                <li key={benefit}>{benefit}</li>
              ))}
            </ul>
          ) : null}
        </SidePanel>
      ) : null}
    </div>
  )
}

function RewardChip({
  reward,
  compact,
  onClick,
}: {
  reward: Reward
  compact: boolean
  onClick: () => void
}) {
  const urgency = expiryUrgency(reward.expires_at)
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 border-2 border-line bg-white px-1.5 py-1 text-left font-bold text-ink ${compact ? 'text-[11px]' : 'text-xs'}`}
    >
      <ExpiryRing
        fraction={expiryFraction(reward.created_at, reward.expires_at)}
        urgency={urgency}
        size={compact ? 12 : 16}
        stroke={3}
      />
      <span className="min-w-0 truncate">
        {reward.merchant_name}
        {compact ? '' : ` · ${formatRewardValue(reward)}`}
      </span>
    </button>
  )
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-3 w-3 border-2 border-line ${swatch}`} />
      {label}
    </span>
  )
}
