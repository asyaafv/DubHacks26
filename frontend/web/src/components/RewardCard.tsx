import type { Reward } from '../types'
import { domainFor } from '../util/merchants'
import {
  expiryUrgency,
  formatExpiry,
  formatRewardValue,
  needsReview,
  URGENCY_TEXT,
} from '../util/rewards'
import { MerchantLogo } from './MerchantLogo'
import { ReviewBadge } from './ReviewBadge'

export function RewardCard({ reward, onClick }: { reward: Reward; onClick: () => void }) {
  const domain = domainFor(reward.merchant_name, reward.merchant_id)
  const urgency = expiryUrgency(reward.expires_at)

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="reward-card"
      className="flex w-full gap-3 rounded-2xl border border-line bg-white p-4 text-left shadow-card transition hover:border-accent"
    >
      <MerchantLogo name={reward.merchant_name} domain={domain} />
      <span className="min-w-0 flex-1">
        <span className="flex items-start justify-between gap-2">
          <span className="truncate font-semibold text-ink">{reward.merchant_name}</span>
          {needsReview(reward) ? <ReviewBadge /> : null}
        </span>
        <span className="mt-1 block font-medium text-accent">{formatRewardValue(reward)}</span>
        <span className={`mt-1 block text-sm ${URGENCY_TEXT[urgency]}`}>{formatExpiry(reward.expires_at)}</span>
      </span>
    </button>
  )
}
