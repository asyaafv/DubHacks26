import { useMemo } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useRewards } from '../context/RewardsContext'
import { useSession } from '../context/SessionContext'
import { daysUntil } from '../util/dates'
import { formatExpiry, formatRewardValue, isOpenReward } from '../util/rewards'
import { ExpiryRing } from './ExpiryRing'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Rewards' },
  { to: '/savings', label: 'Savings' },
  { to: '/calendar', label: 'Calendar' },
]

export function AppShell() {
  const { user } = useSession()
  const { rewards } = useRewards()

  // One ticker segment; rendered twice so the -50% scroll loops seamlessly.
  const tickerSegment = useMemo(() => {
    const expiring = rewards
      .filter((reward) => {
        if (!isOpenReward(reward) || !reward.expires_at) return false
        const days = daysUntil(reward.expires_at)
        return days !== null && days >= 0 && days <= 7
      })
      .sort(
        (a, b) =>
          (a.expires_at ?? '').localeCompare(b.expires_at ?? '') ||
          a.merchant_name.localeCompare(b.merchant_name),
      )
    if (expiring.length === 0) return ''
    const line = expiring
      .map(
        (reward) =>
          `${reward.merchant_name.toUpperCase()} ${formatRewardValue(reward)} — ${formatExpiry(reward.expires_at).toUpperCase()}`,
      )
      .join('  ✂  ')
    return `${line}  ✂  `
  }, [rewards])

  return (
    <div className="min-h-screen bg-paper text-ink">
      {tickerSegment ? (
        <div
          aria-hidden
          className="overflow-hidden whitespace-nowrap border-b-2 border-line bg-ink py-1.5 text-xs font-bold tracking-wider text-lime"
        >
          <div className="ticker-track inline-block">{`${tickerSegment}${tickerSegment}`}</div>
        </div>
      ) : null}
      <header className="border-b-2 border-line bg-tangerine">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/dashboard" className="flex items-center gap-2">
            <ExpiryRing fraction={0.65} urgency="later" size={30} stroke={5} />
            <span className="font-display text-3xl font-black uppercase tracking-tight text-white">
              Lapse
            </span>
          </Link>
          <nav className="flex items-center gap-2 text-xs font-black uppercase">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `border-2 border-line px-3 py-1 ${isActive ? 'bg-ink text-lime' : 'bg-white text-ink'}`
                }
              >
                {item.label}
              </NavLink>
            ))}
            {user ? <span className="border-2 border-line bg-lilac px-3 py-1 text-ink">{user.email}</span> : null}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
