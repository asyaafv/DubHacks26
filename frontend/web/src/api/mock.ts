import cardsFile from '../../../../shared/seed/seed_cards.json'
import membershipsFile from '../../../../shared/seed/seed_memberships.json'
import rewardsFile from '../../../../shared/seed/seed_rewards.json'
import type { SavingsItem, SavingsResponse } from './savings'
import { extraRewards } from './extras'
import type { Card, Membership, Reward, SyncResponse, Wallet } from '../types'
import { RewardStatus } from '../types'
import { DEMO_USER } from '../util/demo'
import { buildSeries, sumSaved, toCents } from '../util/money'
import { daysUntil } from '../util/dates'
import { formatRewardValue } from '../util/rewards'

const SESSION_KEY = 'lapse.mock.savings'

/**
 * Eight redemptions across the six weeks before 2026-10-18.
 * 4.75 + 12 + 8.50 + 18 + 10 + 15.26 + 20 + 15 = 103.51
 */
const BASE_ITEMS: SavingsItem[] = [
  {
    reward_id: '22222222-2222-2222-2222-222222222301',
    merchant_name: 'Starbucks',
    description: 'Stars reward',
    saved: '4.75',
    redeemed_at: '2026-09-08T18:12:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222302',
    merchant_name: 'Target',
    description: 'Circle offer',
    saved: '12.00',
    redeemed_at: '2026-09-15T16:40:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222303',
    merchant_name: 'Chipotle',
    description: 'Free guacamole',
    saved: '8.50',
    redeemed_at: '2026-09-22T19:05:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222304',
    merchant_name: 'Nike',
    description: 'Member discount',
    saved: '18.00',
    redeemed_at: '2026-09-28T21:15:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222305',
    merchant_name: 'Amazon',
    description: 'Promo code',
    saved: '10.00',
    redeemed_at: '2026-10-02T15:22:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222306',
    merchant_name: 'Sephora',
    description: 'Beauty Insider',
    saved: '15.26',
    redeemed_at: '2026-10-06T17:48:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222307',
    merchant_name: 'Gap',
    description: 'Weekend promo',
    saved: '20.00',
    redeemed_at: '2026-10-10T20:11:00Z',
  },
  {
    reward_id: '22222222-2222-2222-2222-222222222308',
    merchant_name: 'Old Navy',
    description: 'App offer',
    saved: '15.00',
    redeemed_at: '2026-10-14T18:36:00Z',
  },
]

const baseTotal = BASE_ITEMS.reduce((sum, item) => sum + toCents(item.saved), 0)
if (baseTotal !== 10351) {
  throw new Error(`Demo savings seed must total 103.51, got ${baseTotal} cents`)
}

function seedRewards(): Reward[] {
  const seeded = (rewardsFile as { rewards: Reward[] }).rewards
  return structuredClone([...seeded, ...extraRewards])
}

function readItems(): SavingsItem[] {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return structuredClone(BASE_ITEMS)
    const parsed = JSON.parse(raw) as SavingsItem[]
    if (!Array.isArray(parsed) || parsed.length < BASE_ITEMS.length) return structuredClone(BASE_ITEMS)
    return parsed
  } catch {
    return structuredClone(BASE_ITEMS)
  }
}

function writeItems(items: SavingsItem[]): void {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(items))
}

const rewards = seedRewards()
let items = readItems()

function applyRedeemedStatus(): void {
  const redeemed = new Set(items.map((item) => item.reward_id))
  for (const reward of rewards) {
    if (redeemed.has(reward.id)) reward.status = RewardStatus.used
  }
}

applyRedeemedStatus()

function walletFor(userId: string, visible: Reward[]): Wallet {
  const cards = (cardsFile as { cards: Card[] }).cards.filter((card) => card.user_id === userId)
  const memberships = (membershipsFile as { memberships: Membership[] }).memberships.filter(
    (membership) => membership.user_id === userId,
  )
  const open = visible.filter(
    (reward) => reward.status === RewardStatus.active || reward.status === RewardStatus.needs_review,
  )
  return {
    user_id: userId,
    cards,
    memberships,
    active_rewards_count: open.length,
    expiring_soon_count: open.filter((reward) => {
      const days = daysUntil(reward.expires_at)
      return days !== null && days >= 0 && days <= 3
    }).length,
  }
}

function savingsResponse(): SavingsResponse {
  return {
    total: sumSaved(items),
    items: structuredClone(items),
    series: buildSeries(items),
  }
}

export const mockApi = {
  async getSync(userId: string): Promise<SyncResponse> {
    const mine = rewards.filter((reward) => reward.user_id === userId)
    const visible = mine.filter(
      (reward) => reward.status === RewardStatus.active || reward.status === RewardStatus.needs_review,
    )
    return {
      user_id: userId,
      rewards: structuredClone(visible),
      wallet: walletFor(userId, mine),
      last_sync: new Date().toISOString(),
      pending_events: [],
    }
  },

  async getSavings(userId: string): Promise<SavingsResponse> {
    if (userId !== DEMO_USER.id) {
      return { total: '0.00', items: [], series: [] }
    }
    return savingsResponse()
  },

  async redeem(userId: string, rewardId: string, saved: string): Promise<Reward> {
    const amount = Number(saved)
    if (!Number.isFinite(amount) || amount < 0) {
      throw new Error('Saved amount must be a non-negative number')
    }
    const reward = rewards.find((item) => item.id === rewardId && item.user_id === userId)
    if (!reward) throw new Error('Reward not found')
    reward.status = RewardStatus.used
    reward.updated_at = new Date().toISOString()
    items = [
      {
        reward_id: reward.id,
        merchant_name: reward.merchant_name,
        description: formatRewardValue(reward),
        saved: amount.toFixed(2),
        redeemed_at: new Date().toISOString(),
      },
      ...items,
    ]
    try {
      writeItems(items)
    } catch {
      // The in-memory ledger still updates if the browser blocks storage.
    }
    return structuredClone(reward)
  },
}
