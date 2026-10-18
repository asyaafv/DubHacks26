import { describe, expect, it } from 'vitest';
import { expiryFraction, urgencyFromDays } from './ExpiryRing';

describe('ExpiryRing helpers', () => {
  it('maps days until expiry to urgency buckets', () => {
    expect(urgencyFromDays(null)).toBe('none');
    expect(urgencyFromDays(undefined)).toBe('none');
    expect(urgencyFromDays(0)).toBe('soon');
    expect(urgencyFromDays(3)).toBe('soon');
    expect(urgencyFromDays(7)).toBe('week');
    expect(urgencyFromDays(8)).toBe('later');
  });

  it('computes the remaining fraction of the reward lifetime', () => {
    const created = '2026-10-10T00:00:00Z';
    const expires = '2026-10-20T00:00:00Z';
    expect(expiryFraction(created, expires, new Date('2026-10-15T00:00:00Z'))).toBeCloseTo(0.5);
    expect(expiryFraction(created, expires, new Date('2026-10-25T00:00:00Z'))).toBe(0);
    expect(expiryFraction(created, expires, new Date('2026-10-01T00:00:00Z'))).toBe(1);
  });

  it('falls back to a 14-day window when created_at is missing', () => {
    const expires = '2026-10-20T00:00:00Z';
    // 7 of the assumed 14 days remain.
    expect(expiryFraction(null, expires, new Date('2026-10-13T00:00:00Z'))).toBeCloseTo(0.5);
    expect(expiryFraction(undefined, null)).toBe(1);
  });
});
