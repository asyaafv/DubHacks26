import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { RewardCard } from '../components/RewardCard'
import { RewardDrawer } from '../components/RewardDrawer'
import { useRewards } from '../context/RewardsContext'
import { useSession } from '../context/SessionContext'
import { copyText } from '../util/copy'
import { daysUntil } from '../util/dates'
import { formatDollars } from '../util/money'
import {
  BUCKETS,
  expiringSoon,
  formatRewardValue,
  groupRewards,
  isOpenReward,
  needsReview,
  rewardBucket,
  type Bucket,
} from '../util/rewards'

export function Dashboard() {
  const { user } = useSession()
  const { rewards, savings, loading, error, redeem } = useRewards()
  const [query, setQuery] = useState('')
  const [bucket, setBucket] = useState<Bucket | 'All'>('All')
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const open = useMemo(() => rewards.filter(isOpenReward), [rewards])
  const soon = useMemo(() => expiringSoon(open), [open])
  const lapsingIn3 = useMemo(
    () =>
      open.filter((reward) => {
        const days = daysUntil(reward.expires_at)
        return days !== null && days >= 0 && days <= 3
      }),
    [open],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return open.filter((reward) => {
      if (bucket !== 'All' && rewardBucket(reward) !== bucket) return false
      if (needsReviewOnly && !needsReview(reward)) return false
      if (!q) return true
      const haystack = [
        reward.merchant_name,
        reward.code ?? '',
        reward.category,
        rewardBucket(reward),
        formatRewardValue(reward),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(q)
    })
  }, [open, query, bucket, needsReviewOnly])

  const groups = useMemo(() => groupRewards(filtered), [filtered])
  const selected = rewards.find((reward) => reward.id === selectedId) ?? null

  async function copyAddress() {
    if (!user) return
    const ok = await copyText(user.email)
    setCopied(ok)
    if (ok) window.setTimeout(() => setCopied(false), 1500)
  }

  async function handleRedeem(saved: string) {
    if (!selected) return
    const merchant = selected.merchant_name
    await redeem(selected.id, saved)
    setSelectedId(null)
    setNotice(`Marked ${merchant} as used · ${formatDollars(saved)} saved`)
  }

  const stats = [
    {
      label: 'Saved so far',
      value: savings ? formatDollars(savings.total) : '—',
      bg: 'bg-lime text-ink',
      testId: 'total-savings',
      to: '/savings',
    },
    { label: 'Rewards clipped', value: String(open.length), bg: 'bg-white text-ink' },
    { label: 'Lapse in 3 days', value: String(lapsingIn3.length), bg: 'bg-tangerine text-white', to: '/calendar' },
    { label: 'Used', value: String(savings?.items.length ?? 0), bg: 'bg-sky text-ink' },
  ]

  return (
    <div>
      <section className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-display text-4xl font-black uppercase tracking-tight text-ink">
          Check out your rewards
        </h1>
        <div className="inline-flex items-center gap-3 border-2 border-line bg-white px-4 py-2 shadow-card">
          <span className="text-sm font-bold text-ink">{user?.email}</span>
          <button
            type="button"
            onClick={() => void copyAddress()}
            className="border-2 border-line bg-lime px-3 py-1 text-xs font-black uppercase text-ink"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </section>

      {error ? (
        <p className="mb-6 border-2 border-line bg-tangerine px-4 py-3 text-sm font-bold text-white shadow-card">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="mb-6 border-2 border-line bg-lime px-4 py-3 text-sm font-bold text-ink shadow-card">
          {notice}
        </p>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((stat) => {
          const body = (
            <>
              <span className="block text-[11px] font-black uppercase tracking-wider">{stat.label}</span>
              <span
                {...(stat.testId ? { 'data-testid': stat.testId } : {})}
                className="block font-display text-4xl font-black leading-tight"
              >
                {stat.value}
              </span>
            </>
          )
          return stat.to ? (
            <Link key={stat.label} to={stat.to} className={`border-2 border-line px-4 py-3 shadow-stamp ${stat.bg}`}>
              {body}
            </Link>
          ) : (
            <div key={stat.label} className={`border-2 border-line px-4 py-3 shadow-stamp ${stat.bg}`}>
              {body}
            </div>
          )
        })}
      </div>

      {soon.length > 0 ? (
        <div className="mt-6 flex rotate-[-0.4deg] flex-wrap items-center gap-3 border-2 border-line bg-amber px-4 py-2 shadow-stamp">
          <span aria-hidden className="text-xl">
            ✂
          </span>
          <p className="min-w-0 flex-1 text-sm font-bold uppercase text-ink">
            Clip &rsquo;em before they lapse:{' '}
            {soon
              .slice(0, 3)
              .map((reward) => `${formatRewardValue(reward)} at ${reward.merchant_name}`)
              .join(', ')}{' '}
            up next{lapsingIn3.length > 0 ? ` — ${lapsingIn3.length} die within 3 days` : ''}
          </p>
          <Link to="/calendar" className="shrink-0 border-2 border-line bg-white px-2 py-1 text-xs font-black uppercase text-ink">
            Full calendar
          </Link>
        </div>
      ) : null}

      <section className="mt-8">
        <div className="mb-4 flex items-end justify-between gap-4">
          <h2 className="font-display text-2xl font-black uppercase text-ink">Your rewards</h2>
          <span className="text-sm font-bold text-muted">{loading ? 'Loading…' : `${filtered.length} shown`}</span>
        </div>
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="reward-search">
            Search rewards
          </label>
          <input
            id="reward-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search merchants, codes, offers"
            className="w-full max-w-sm border-2 border-line bg-white px-3 py-2 text-sm font-semibold shadow-card outline-none focus:border-tangerine"
          />
          {(['All', ...BUCKETS] as const).map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={bucket === item}
              onClick={() => setBucket(item)}
              className={`border-2 border-line px-3 py-1.5 text-xs font-black uppercase ${
                bucket === item ? 'bg-ink text-lime' : 'bg-white text-ink'
              }`}
            >
              {item}
            </button>
          ))}
          <button
            type="button"
            aria-pressed={needsReviewOnly}
            onClick={() => setNeedsReviewOnly((value) => !value)}
            className={`border-2 border-line px-3 py-1.5 text-xs font-black uppercase ${
              needsReviewOnly ? 'bg-ink text-lime' : 'bg-white text-ink'
            }`}
          >
            Needs review
          </button>
        </div>

        {loading ? <p className="text-sm font-bold text-muted">Loading rewards…</p> : null}
        {!loading && filtered.length === 0 ? (
          <p className="border-2 border-dashed border-line bg-white px-4 py-8 text-center text-sm font-bold uppercase text-muted">
            No rewards match.
          </p>
        ) : null}

        <div className="space-y-10">
          {BUCKETS.map((name) => {
            const list = groups[name]
            if (list.length === 0) return null
            return (
              <div key={name}>
                <h3 className="mb-4 inline-block -rotate-1 border-2 border-line bg-white px-3 py-1 font-display text-xl font-black uppercase text-ink shadow-card">
                  {name} · {list.length}
                </h3>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {list.map((reward) => (
                    <RewardCard key={reward.id} reward={reward} onClick={() => setSelectedId(reward.id)} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {selected ? (
        <RewardDrawer key={selected.id} reward={selected} onClose={() => setSelectedId(null)} onRedeem={handleRedeem} />
      ) : null}
    </div>
  )
}
