import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api'
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

export function RewardsProvider({ children }: { children: ReactNode }) {
  const { user } = useSession()
  const [rewards, setRewards] = useState<Reward[]>([])
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [savings, setSavings] = useState<SavingsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    let cancelled = false
    setLoading(true)
    Promise.all([api.getSync(user.id), api.getSavings(user.id)])
      .then(([sync, nextSavings]) => {
        if (cancelled) return
        setRewards(sync.rewards ?? [])
        setWallet(sync.wallet)
        setSavings(nextSavings)
        setError(null)
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
    }
  }, [user])

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
