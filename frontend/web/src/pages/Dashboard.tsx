import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { RewardCard } from '../components/RewardCard'
import { RewardDrawer } from '../components/RewardDrawer'
import { useRewards } from '../context/RewardsContext'
import { useSession } from '../context/SessionContext'
import { copyText } from '../util/copy'
import { formatDollars } from '../util/money'
import { domainFor } from '../util/merchants'
import {
  BUCKETS,
  expiringSoon,
  expiryUrgency,
  formatExpiry,
  formatRewardValue,
  groupRewards,
  isOpenReward,
  needsReview,
  rewardBucket,
  URGENCY_TEXT,
  type Bucket,
} from '../util/rewards'
import { MerchantLogo } from '../components/MerchantLogo'
import { RewardStatus, type Reward } from '../types'

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

  return (
    <div>
      <section className="mb-8">
        <h1 className="font-serif text-4xl tracking-tight text-ink">Check out your rewards</h1>
        <div className="mt-4 inline-flex items-center gap-3 rounded-full border border-line bg-white px-4 py-2 shadow-card">
          <span className="font-medium text-ink">{user?.email}</span>
          <button type="button" onClick={() => void copyAddress()} className="text-sm font-semibold text-accent">
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </section>

      {error ? (
        <p className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</p>
      ) : null}
      {notice ? (
        <p role="status" className="mb-6 rounded-2xl border border-accent/20 bg-accent-soft px-4 py-3 text-sm text-accent-dark">
          {notice}
        </p>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)_320px] items-start gap-8">
        <section>
          <div className="mb-4 flex items-end justify-between gap-4">
            <h2 className="font-serif text-2xl text-ink">Your rewards</h2>
            <span className="text-sm text-muted">{loading ? 'Loading…' : `${filtered.length} shown`}</span>
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="reward-search">
              Search rewards
            </label>
            <input
              id="reward-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search merchants, codes, offers"
              className="w-full max-w-sm rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:border-accent"
            />
            {(['All', ...BUCKETS] as const).map((item) => (
              <button
                key={item}
                type="button"
                aria-pressed={bucket === item}
                onClick={() => setBucket(item)}
                className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                  bucket === item ? 'bg-accent text-white' : 'border border-line bg-white text-ink'
                }`}
              >
                {item}
              </button>
            ))}
            <button
              type="button"
              aria-pressed={needsReviewOnly}
              onClick={() => setNeedsReviewOnly((value) => !value)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium ${
                needsReviewOnly ? 'bg-accent text-white' : 'border border-line bg-white text-ink'
              }`}
            >
              Needs review
            </button>
          </div>

          {loading ? <p className="text-sm text-muted">Loading rewards…</p> : null}
          {!loading && filtered.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-line bg-white px-4 py-8 text-center text-sm text-muted">
              No rewards match.
            </p>
          ) : null}

          <div className="space-y-8">
            {BUCKETS.map((name) => {
              const list = groups[name]
              if (list.length === 0) return null
              return (
                <div key={name}>
                  <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-muted">{name}</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {list.map((reward) => (
                      <RewardCard key={reward.id} reward={reward} onClick={() => setSelectedId(reward.id)} />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted">Total savings</h2>
            <p data-testid="total-savings" className="mt-3 font-serif text-5xl tracking-tight text-ink">
              {savings ? formatDollars(savings.total) : '—'}
            </p>
            <Link to="/savings" className="mt-4 inline-flex text-sm font-semibold text-accent">
              View details
            </Link>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted">Expiring soon</h2>
            <ul className="mt-4 space-y-3">
              {soon.map((reward) => (
                <li key={reward.id}>
                  <ExpiringRow reward={reward} onClick={() => setSelectedId(reward.id)} />
                </li>
              ))}
              {soon.length === 0 ? <li className="text-sm text-muted">Nothing expiring.</li> : null}
            </ul>
            <Link to="/calendar" className="mt-4 inline-flex text-sm font-semibold text-accent">
              Full calendar
            </Link>
          </section>
        </aside>
      </div>

      {selected ? (
        <RewardDrawer key={selected.id} reward={selected} onClose={() => setSelectedId(null)} onRedeem={handleRedeem} />
      ) : null}
    </div>
  )
}

function ExpiringRow({ reward, onClick }: { reward: Reward; onClick: () => void }) {
  const urgency = expiryUrgency(reward.expires_at)
  return (
    <button type="button" onClick={onClick} className="flex w-full items-center gap-3 text-left">
      <MerchantLogo name={reward.merchant_name} domain={domainFor(reward.merchant_name, reward.merchant_id)} size={32} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-ink">
          {reward.merchant_name}
          {reward.status === RewardStatus.needs_review ? ' · Needs review' : ''}
        </span>
        <span className={`block truncate text-xs ${URGENCY_TEXT[urgency]}`}>
          {formatRewardValue(reward)} · {formatExpiry(reward.expires_at)}
        </span>
      </span>
    </button>
  )
}
