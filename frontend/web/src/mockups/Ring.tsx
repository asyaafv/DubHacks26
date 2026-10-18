import type { Theme } from './themes'
import type { RingState } from './data'

/**
 * The Lapse brand motif: a countdown ring that drains as a reward nears
 * expiration. fraction=1 full window left, 0 lapsed.
 */
export function ExpiryRing({
  state,
  theme,
  size = 44,
  stroke = 4,
  children,
}: {
  state: RingState
  theme: Theme
  size?: number
  stroke?: number
  children?: React.ReactNode
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const color = theme.ring[state.urgency]
  const dash = c * state.fraction
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={theme.ring.track} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          style={theme.glow ? { filter: `drop-shadow(0 0 4px ${color})` } : undefined}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">{children}</div>
    </div>
  )
}

/** Compact days-left label used inside rings. */
export function RingDays({ state, className }: { state: RingState; className?: string }) {
  return (
    <span className={className}>
      {state.daysLeft === null ? '∞' : state.daysLeft === 0 ? '0d' : `${state.daysLeft}d`}
    </span>
  )
}
