import type { ReactNode } from 'react';

/** Lapse brand motif: a ring that drains as a reward nears expiration. */

export type ExpiryUrgency = 'soon' | 'week' | 'later' | 'none';

export const URGENCY_COLORS: Record<ExpiryUrgency, string> = {
  soon: '#FF5C1C',
  week: '#F5A800',
  later: '#141414',
  none: '#9a9a9a',
};

export const RING_TRACK_COLOR = '#EFE3CB';

/** Assumed reward lifetime when the backend did not record created_at. */
const FALLBACK_WINDOW_MS = 14 * 86_400_000;

/** Map whole days until expiry (from core/format daysUntilExpiry) to a ring color bucket. */
export function urgencyFromDays(days: number | null | undefined): ExpiryUrgency {
  if (days == null) return 'none';
  if (days <= 3) return 'soon';
  if (days <= 7) return 'week';
  return 'later';
}

/**
 * Fraction of the reward's lifetime remaining, clamped to 0..1.
 * Falls back to a 14-day window when created_at is missing or inconsistent.
 */
export function expiryFraction(
  createdAt: string | null | undefined,
  expiresAt: string | null | undefined,
  now: Date = new Date(),
): number {
  if (!expiresAt) return 1;
  const expires = new Date(expiresAt).getTime();
  if (Number.isNaN(expires)) return 1;
  let created = createdAt ? new Date(createdAt).getTime() : NaN;
  if (Number.isNaN(created) || created >= expires) created = expires - FALLBACK_WINDOW_MS;
  const fraction = (expires - now.getTime()) / (expires - created);
  return Math.min(1, Math.max(0, fraction));
}

interface ExpiryRingProps {
  /** 0..1 share of the reward lifetime remaining. */
  fraction: number;
  urgency: ExpiryUrgency;
  size?: number;
  stroke?: number;
  children?: ReactNode;
}

export function ExpiryRing({ fraction, urgency, size = 26, stroke = 4, children }: ExpiryRingProps) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * Math.min(1, Math.max(0, fraction));

  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={RING_TRACK_COLOR} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={URGENCY_COLORS[urgency]}
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${circumference}`}
        />
      </svg>
      {children ? <div className="absolute inset-0 grid place-items-center">{children}</div> : null}
    </div>
  );
}
