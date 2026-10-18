import { useState } from 'react'
import type { Reward } from '../types'
import { copyText } from '../util/copy'
import { domainFor } from '../util/merchants'
import {
  fieldNeedsReview,
  formatExpiry,
  formatMoneyOrNone,
  formatRewardValue,
  needsReview,
  rewardTerms,
  suggestedSaved,
} from '../util/rewards'
import { MerchantLogo } from './MerchantLogo'
import { ReviewBadge } from './ReviewBadge'
import { SidePanel } from './SidePanel'

const FIELD_LABELS: { key: 'value' | 'expires_at' | 'code' | 'min_spend' | 'merchant'; label: string }[] = [
  { key: 'value', label: 'Value' },
  { key: 'expires_at', label: 'Expiry' },
  { key: 'code', label: 'Code' },
  { key: 'min_spend', label: 'Minimum spend' },
  { key: 'merchant', label: 'Merchant' },
]

export function RewardDrawer({
  reward,
  onClose,
  onRedeem,
}: {
  reward: Reward
  onClose: () => void
  onRedeem: (saved: string) => Promise<void>
}) {
  const [saved, setSaved] = useState(() => suggestedSaved(reward))
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const domain = domainFor(reward.merchant_name, reward.merchant_id)
  const confidence = reward.overall_confidence

  async function copyCode() {
    if (!reward.code) return
    const ok = await copyText(reward.code)
    setCopied(ok)
    if (ok) window.setTimeout(() => setCopied(false), 1500)
  }

  async function submit() {
    const amount = Number(saved)
    if (!Number.isFinite(amount) || amount < 0) {
      setFormError('Enter a dollar amount saved, like 10.00')
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await onRedeem(amount.toFixed(2))
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not mark this reward as used')
      setBusy(false)
    }
  }

  return (
    <SidePanel title="More details" onClose={onClose}>
      <div className="flex items-start gap-3">
        <MerchantLogo name={reward.merchant_name} domain={domain} size={48} />
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-xl font-semibold text-ink">{reward.merchant_name}</h3>
            {needsReview(reward) ? <ReviewBadge /> : null}
          </div>
          <p className="mt-1 text-lg font-medium text-accent">{formatRewardValue(reward)}</p>
          <p className="mt-1 text-sm text-muted">{formatExpiry(reward.expires_at)}</p>
        </div>
      </div>

      <dl className="mt-6 space-y-4 text-sm">
        <div>
          <dt className="font-medium text-ink">Code</dt>
          <dd className="mt-1 flex items-center gap-2">
            <code className="rounded-lg bg-paper px-2 py-1 text-ink">{reward.code || 'No code'}</code>
            {reward.code ? (
              <button type="button" onClick={() => void copyCode()} className="text-sm font-medium text-accent">
                {copied ? 'Copied' : 'Copy'}
              </button>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink">Terms</dt>
          <dd className="mt-1 leading-relaxed text-muted">{rewardTerms(reward)}</dd>
        </div>
        <div>
          <dt className="font-medium text-ink">Minimum spend</dt>
          <dd className="mt-1 text-muted">{formatMoneyOrNone(reward.min_spend)}</dd>
        </div>
        <div>
          <dt className="font-medium text-ink">Exclusions</dt>
          <dd className="mt-1 text-muted">
            {reward.exclusions && reward.exclusions.length > 0 ? reward.exclusions.join(', ') : 'None'}
          </dd>
        </div>
        <div>
          <dt className="font-medium text-ink">Confidence</dt>
          <dd className="mt-1 text-muted">
            {confidence == null ? 'Not scored' : `${Math.round(confidence * 100)}% overall`}
          </dd>
          {reward.field_confidence ? (
            <ul className="mt-2 space-y-1">
              {FIELD_LABELS.map((field) => {
                const score = reward.field_confidence?.[field.key]
                return (
                  <li key={field.key} className="flex items-center justify-between gap-3 text-muted">
                    <span>{field.label}</span>
                    <span className="flex items-center gap-2">
                      {score == null ? '—' : `${Math.round(score * 100)}%`}
                      {fieldNeedsReview(reward, score) ? <ReviewBadge /> : null}
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : null}
        </div>
      </dl>

      {needsReview(reward) || reward.status === 'active' || reward.status == null ? (
        <form
          className="mt-8 border-t border-line pt-5"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <label htmlFor="saved-amount" className="text-sm font-medium text-ink">
            Amount saved
          </label>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-muted">$</span>
            <input
              id="saved-amount"
              inputMode="decimal"
              value={saved}
              onChange={(event) => setSaved(event.target.value)}
              className="w-full rounded-xl border border-line px-3 py-2 outline-none focus:border-accent"
            />
          </div>
          {formError ? <p className="mt-2 text-sm text-rose-700">{formError}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="mt-4 w-full rounded-full bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? 'Saving…' : 'Mark as used'}
          </button>
        </form>
      ) : (
        <p className="mt-8 text-sm text-muted">This reward is already used.</p>
      )}
    </SidePanel>
  )
}
