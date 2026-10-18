import type { Reward } from '../types'
import { daysUntil } from '../util/dates'
import { domainFor } from '../util/merchants'
import {
  expiryUrgency,
  formatExpiry,
  formatPlainNumber,
  formatRewardValue,
  needsReview,
} from '../util/rewards'
import { ExpiryRing, expiryFraction } from './ExpiryRing'
import { MerchantLogo } from './MerchantLogo'
import { ReviewBadge } from './ReviewBadge'

export function RewardCard({ reward, onClick }: { reward: Reward; onClick: () => void }) {
  const domain = domainFor(reward.merchant_name, reward.merchant_id)
  const urgency = expiryUrgency(reward.expires_at)
  const days = daysUntil(reward.expires_at)

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="reward-card"
      className="relative block w-full border-2 border-line bg-white text-left shadow-card transition hover:-translate-y-0.5"
    >
      {urgency === 'soon' && days !== null ? (
        <span className="absolute -right-2 -top-3 z-10 rotate-6 border-2 border-line bg-tangerine px-2 py-0.5 font-display text-[10px] font-black uppercase text-white">
          {days === 0 ? 'today!' : days === 1 ? 'tomorrow!' : `${days} days!`}
        </span>
      ) : null}
      <span className="flex items-center gap-2 border-b-2 border-dashed border-line px-3 py-2">
        <MerchantLogo name={reward.merchant_name} domain={domain} size={30} />
        <span className="min-w-0 flex-1 truncate text-sm font-bold uppercase text-ink">
          {reward.merchant_name}
        </span>
        {needsReview(reward) ? <ReviewBadge /> : null}
        <ExpiryRing
          fraction={expiryFraction(reward.created_at, reward.expires_at)}
          urgency={urgency}
          size={26}
          stroke={4}
        />
      </span>
      <span className="block px-3 py-2">
        <span className="block font-display text-2xl font-black leading-none text-ink">
          {formatRewardValue(reward)}
        </span>
        <span className="mt-1 block text-[11px] font-semibold text-muted">
          {formatExpiry(reward.expires_at)}
          {reward.min_spend ? ` · min $${formatPlainNumber(reward.min_spend)}` : ''}
        </span>
      </span>
      {reward.code ? (
        <span className="flex items-center justify-between gap-2 border-t-2 border-line bg-paper px-3 py-1.5">
          <span aria-hidden className="barcode h-5 w-16" />
          <span className="text-xs font-black tracking-widest text-ink">{reward.code}</span>
        </span>
      ) : null}
    </button>
  )
}
