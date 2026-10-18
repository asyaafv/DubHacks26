import type { ReactNode } from 'react'
import type { Urgency } from '../util/dates'

/** Direction B ring colors by urgency. */
const RING_COLOR: Record<Urgency, string> = {
  soon: '#FF5C1C',
  week: '#F5A800',
  later: '#141414',
  none: '#9a9a9a',
}
const TRACK = '#EFE3CB'

/**
 * The Lapse brand motif: a countdown ring that drains as a reward nears
 * expiration. fraction=1 full window left, 0 lapsed.
 */
export function ExpiryRing({
  fraction,
  urgency,
  size = 28,
  stroke = 4,
  children,
}: {
  fraction: number
  urgency: Urgency
  size?: number
  stroke?: number
  children?: ReactNode
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.min(1, Math.max(0, fraction))
  const dash = c * clamped
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} aria-hidden>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={TRACK} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={RING_COLOR[urgency]}
          strokeWidth={stroke}
          strokeLinecap="butt"
          strokeDasharray={`${dash} ${c - dash}`}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  )
}

/**
 * Time-remaining fraction of the reward's life (created_at → expires_at).
 * Falls back to a 14-day window when created_at is missing.
 */
export function expiryFraction(
  createdAt: string | null | undefined,
  expiresAt: string | null | undefined,
  now: Date = new Date(),
): number {
  if (!expiresAt) return 1
  const end = new Date(expiresAt).getTime()
  const start = createdAt ? new Date(createdAt).getTime() : now.getTime() - 14 * 86400000
  const span = Math.max(end - start, 1)
  return Math.min(1, Math.max(0, (end - now.getTime()) / span))
}
