import { TERMS_OVERRIDES, VALUE_LABELS } from '../api/extras'
import { RewardKind, RewardStatus, type Reward } from '../types'
import { daysUntil, formatDateTime, type Urgency, urgencyFor } from './dates'

export const BUCKETS = ['Food', 'Clothing', 'Misc'] as const
export type Bucket = (typeof BUCKETS)[number]

const FOOD_MCCS = new Set(['5411', '5422', '5441', '5451', '5462', '5499', '5812', '5813', '5814'])
const CLOTHING_MCCS = new Set(['5611', '5621', '5631', '5641', '5651', '5655', '5661', '5691', '5699'])

export function rewardBucket(reward: Pick<Reward, 'mcc' | 'category'>): Bucket {
  if (FOOD_MCCS.has(reward.mcc) || /restaurant|fast food|grocery|eating/i.test(reward.category)) {
    return 'Food'
  }
  if (CLOTHING_MCCS.has(reward.mcc) || /clothing|shoe|apparel/i.test(reward.category)) {
    return 'Clothing'
  }
  return 'Misc'
}

export function isOpenReward(reward: Reward): boolean {
  return reward.status !== RewardStatus.used && reward.status !== RewardStatus.expired
}

export function formatPlainNumber(value: number | string): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  return n.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

export function formatRewardValue(reward: Reward): string {
  const override = VALUE_LABELS[reward.id]
  if (override) return override
  const n = formatPlainNumber(reward.value)
  switch (reward.kind) {
    case RewardKind.percent_off:
      return `${n}% off`
    case RewardKind.amount_off:
      return `$${n} off`
    case RewardKind.points:
      return `${n} points`
    case RewardKind.free_item:
      return 'Free item'
    case RewardKind.bogo:
      return 'BOGO'
    case RewardKind.cashback:
      return `${n}% cashback`
    default:
      return n
  }
}

export function rewardTerms(reward: Reward): string {
  const override = TERMS_OVERRIDES[reward.id]
  if (override) return override
  const bits: string[] = []
  bits.push(
    reward.stackable === false
      ? 'Cannot be combined with other rewards.'
      : 'Can be combined with other rewards.',
  )
  if (reward.max_discount != null && reward.max_discount !== '') {
    bits.push(`Discount capped at $${formatPlainNumber(reward.max_discount)}.`)
  }
  if (reward.starts_at) {
    bits.push(`Starts ${formatDateTime(reward.starts_at)}.`)
  }
  return bits.join(' ')
}

export function suggestedSaved(reward: Reward): string {
  if (reward.kind === RewardKind.amount_off) {
    return Number(reward.value).toFixed(2)
  }
  return '10.00'
}

export function formatExpiry(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return 'No expiry'
  const days = daysUntil(iso, now)
  const date = new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
  if (days === null) return date
  if (days < 0) return `Expired ${date}`
  if (days === 0) return 'Expires today'
  if (days === 1) return 'Expires tomorrow'
  if (days <= 7) return `Expires in ${days} days`
  return `Expires ${date}`
}

export function expiryUrgency(iso: string | null | undefined, now = new Date()): Urgency {
  return urgencyFor(daysUntil(iso, now))
}

export function groupRewards(rewards: Reward[]): Record<Bucket, Reward[]> {
  const groups: Record<Bucket, Reward[]> = { Food: [], Clothing: [], Misc: [] }
  for (const reward of rewards) {
    groups[rewardBucket(reward)].push(reward)
  }
  for (const bucket of BUCKETS) {
    groups[bucket].sort((a, b) => {
      const left = a.expires_at ?? '9999'
      const right = b.expires_at ?? '9999'
      return left.localeCompare(right) || a.merchant_name.localeCompare(b.merchant_name)
    })
  }
  return groups
}

export function expiringSoon(rewards: Reward[], limit = 5): Reward[] {
  return rewards
    .filter((reward) => isOpenReward(reward) && reward.expires_at)
    .sort(
      (a, b) =>
        (a.expires_at ?? '').localeCompare(b.expires_at ?? '') ||
        a.merchant_name.localeCompare(b.merchant_name),
    )
    .slice(0, limit)
}

export function needsReview(reward: Reward): boolean {
  return reward.status === RewardStatus.needs_review
}

export function fieldNeedsReview(reward: Reward, score: number | undefined): boolean {
  return needsReview(reward) && score != null && score < 0.8
}

export function formatMoneyOrNone(value: number | string | null | undefined): string {
  if (value == null || value === '') return 'None'
  return `$${formatPlainNumber(value)}`
}

export const URGENCY_CHIP: Record<Urgency, string> = {
  soon: 'bg-rose-100 text-rose-900',
  week: 'bg-amber-100 text-amber-950',
  later: 'bg-accent-soft text-accent-dark',
  none: 'bg-stone-100 text-stone-700',
}

export const URGENCY_TEXT: Record<Urgency, string> = {
  soon: 'text-rose-700',
  week: 'text-amber-800',
  later: 'text-muted',
  none: 'text-muted',
}
