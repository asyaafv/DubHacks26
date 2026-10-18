import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, API_BASE, getDataSource } from '../api'
import { connectEvents, type ServerEvent } from '../api/events'
import type { SavingsResponse } from '../api/savings'
import type { Reward, Wallet } from '../types'
import { useSession } from './SessionContext'

type RewardsValue = {
  rewards: Reward[]
  wallet: Wallet | null
  savings: SavingsResponse | null
  loading: boolean
  error: string | null
  redeem: (rewardId: string, saved: string) => Promise<Reward>
}

const RewardsContext = createContext<RewardsValue | null>(null)

/** Backend events that mean the reward set or savings ledger changed. */
const REFRESH_EVENTS = new Set(['reward_added', 'reward_updated', 'reward_used', 'reward_expiring'])

export function RewardsProvider({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const [rewards, setRewards] = useState<Reward[]>([])
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [savings, setSavings] = useState<SavingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const refreshTimer = useRef<number | null>(null)

  const load = useCallback(async (userId: string) => {
    const [sync, nextSavings] = await Promise.all([api.getSync(userId), api.getSavings(userId)])
    setRewards(sync.rewards ?? [])
    setWallet(sync.wallet)
    setSavings(nextSavings)
    setError(null)
  }, [])

  useEffect(() => {
    if (!user) return
    let cancelled = false
    const controller = new AbortController()
    setLoading(true)

    const scheduleRefresh = () => {
      if (cancelled) return
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current)
      refreshTimer.current = window.setTimeout(() => {
        refreshTimer.current = null
        void load(user.id).catch(() => {
          // A refresh that fails keeps the last good state; initial-load errors
          // are surfaced below instead.
        })
      }, 250)
    }

    load(user.id)
      .then(() => {
        if (cancelled || getDataSource() !== 'live') return
        // Live mode: stream backend events so injected emails and redemptions
        // show up without a manual reload.
        void connectEvents({
          url: `${API_BASE}/events`,
          userId: user.id,
          signal: controller.signal,
          apply: (event: ServerEvent) => {
            // The stub emits a periodic reward_expiring heartbeat with no
            // reward_id; only real reward mutations trigger a refetch.
            if (REFRESH_EVENTS.has(event.event_type) && event.reward_id) scheduleRefresh()
          },
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'Could not load rewards')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      controller.abort()
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current)
    }
  }, [user, load])

  const redeem = useCallback(
    async (rewardId: string, saved: string) => {
      if (!user) throw new Error('Not signed in')
      const updated = await api.redeem(user.id, rewardId, saved)
      setRewards((current) => current.map((reward) => (reward.id === rewardId ? updated : reward)))
      const nextSavings = await api.getSavings(user.id)
      setSavings(nextSavings)
      return updated
    },
    [user],
  )

  const value = useMemo(
    () => ({ rewards, wallet, savings, loading, error, redeem }),
    [rewards, wallet, savings, loading, error, redeem],
  )

  return <RewardsContext.Provider value={value}>{children}</RewardsContext.Provider>
}

export function useRewards(): RewardsValue {
  const value = useContext(RewardsContext)
  if (!value) throw new Error('useRewards must be used within RewardsProvider')
  return value
}
