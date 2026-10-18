import { describe, expect, it } from 'vitest';
import { daysUntilExpiry, formatExpiry, formatRewardValue, isExpiringSoon } from './format';
import { RewardKind, RewardSource, type Reward } from '../types';

const reward = (kind: RewardKind, value: string): Reward => ({
  id: '1',
  user_id: 'u',
  merchant_name: 'Hollister',
  category: 'Family Clothing Stores',
  mcc: '5651',
  kind,
  value,
  source: RewardSource.seed,
});

describe('format', () => {
  it('counts Hollister expiry as 2 days and flags 3 days or less', () => {
    const days = daysUntilExpiry('2026-10-20T23:59:59Z', new Date('2026-10-18T12:00:00Z'));
    expect(days).toBe(2);
    expect(formatExpiry(days)).toBe('Expires in 2 days');
    expect(isExpiringSoon(days)).toBe(true);
    expect(isExpiringSoon(4)).toBe(false);
  });

  it('formats a percent reward', () => {
    expect(formatRewardValue(reward(RewardKind.percent_off, '10.00'))).toBe('10% off');
  });
});
