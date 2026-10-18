import { describe, expect, it } from 'vitest';
import { applyUseFirst, saveForLaterLabel } from './useFirst';
import { daysUntilExpiry } from './format';
import {
  RewardKind,
  RewardSource,
  RewardStatus,
  type Reward,
  type ScoredReward,
} from '../types';

const NOW = new Date('2026-10-18T12:00:00Z');

function makeReward(overrides: Partial<Reward>): Reward {
  return {
    id: 'r-1',
    user_id: 'u-1',
    merchant_id: 'm-hollister',
    merchant_name: 'Hollister',
    category: 'Family Clothing Stores',
    mcc: '5651',
    kind: RewardKind.percent_off,
    value: '10.00',
    code: 'HCOFALL10',
    stackable: false,
    expires_at: '2026-10-20T23:59:59Z',
    source: RewardSource.seed,
    status: RewardStatus.active,
    ...overrides,
  };
}

function score(reward: Reward, scoreValue = 0.5): ScoredReward {
  return {
    reward,
    score: scoreValue,
    value_component: 0.5,
    match_component: 1,
    urgency_component: 1,
    days_until_expiry: daysUntilExpiry(reward.expires_at, NOW),
  };
}

// A: 25% off expiring in 2 days; B: 10% off good until Nov 17 (30 days out).
const fall = makeReward({ id: 'a', value: '25.00', code: 'HCOFALL25', expires_at: '2026-10-20T23:59:59Z' });
const winter = makeReward({ id: 'b', value: '25.00', code: 'HCOWINTER25', expires_at: '2026-11-17T23:59:59Z' });

describe('applyUseFirst', () => {
  it('flags and reorders a 2-day A against a 30-day B with exact copy', () => {
    const a = score(makeReward({ id: 'a', value: '10.00', code: 'HCOFALL10', expires_at: '2026-10-20T23:59:59Z' }), 0.4);
    const b = score(makeReward({ id: 'b', value: '25.00', code: 'HCOWINTER25', expires_at: '2026-11-17T23:59:59Z' }), 0.9);

    // B outranks A on score alone; the rule must still put A first.
    const result = applyUseFirst([b, a], NOW);

    expect(result.map((item) => item.reward.id)).toEqual(['a', 'b']);
    expect(result[0]?.use_first).toBe(true);
    expect(result[0]?.recommendation).toBe(
      'Use first: expires in 2 days. Your 25% off is good until Nov 17.',
    );
    expect(result[1]?.save_for_later).toBe(true);
    expect(result[1]?.recommendation).toBe('Save for later — good until Nov 17');
    // Inputs are not mutated.
    expect(a.use_first).toBeUndefined();
    expect(b.save_for_later).toBeUndefined();
  });

  it('uses "today" / "in 1 day" phrasing for the A expiry', () => {
    const today = score(makeReward({ id: 'a', expires_at: '2026-10-18T23:59:59Z' }));
    const b = score(winter);
    const result = applyUseFirst([b, today], NOW);
    expect(result[0]?.recommendation).toBe('Use first: expires today. Your 25% off is good until Nov 17.');

    const oneDay = score(makeReward({ id: 'a', expires_at: '2026-10-19T23:59:59Z' }));
    const result2 = applyUseFirst([score(winter), oneDay], NOW);
    expect(result2[0]?.recommendation).toBe('Use first: expires in 1 day. Your 25% off is good until Nov 17.');
  });

  it('treats a never-expiring B as qualifying', () => {
    const a = score(fall);
    const b = score(makeReward({ id: 'b', code: 'HCOEVER', value: '15.00', expires_at: null }));
    const result = applyUseFirst([b, a], NOW);
    expect(result[0]?.use_first).toBe(true);
    expect(result[0]?.recommendation).toBe('Use first: expires in 2 days. Your 15% off never expires.');
    expect(result[1]?.save_for_later).toBe(true);
    expect(result[1]?.recommendation).toBe('Save for later — never expires');
  });

  it('does not apply when A expires in 8 days', () => {
    // 2026-10-26T23:59:59Z is 8 whole days after NOW.
    const a = score(makeReward({ id: 'a', expires_at: '2026-10-26T23:59:59Z' }));
    const b = score(makeReward({ id: 'b', code: 'HCOWINTER25', value: '25.00', expires_at: '2026-12-17T23:59:59Z' }));
    const result = applyUseFirst([b, a], NOW);
    expect(result).toEqual([b, a]);
    expect(result.some((item) => item.use_first || item.save_for_later)).toBe(false);
  });

  it('does not apply when B expires only 13 days after A', () => {
    const a = score(fall);
    // A expires Oct 20; Oct 33 = Nov 2, which is 13 days later.
    const b = score(makeReward({ id: 'b', code: 'HCOWINTER25', value: '25.00', expires_at: '2026-11-02T23:59:59Z' }));
    const result = applyUseFirst([b, a], NOW);
    expect(result).toEqual([b, a]);
  });

  it('does not apply to a stackable, code-free pair (they can combine)', () => {
    const a = score(makeReward({ id: 'a', code: null, stackable: true, expires_at: '2026-10-20T23:59:59Z' }));
    const b = score(makeReward({ id: 'b', code: null, stackable: true, value: '25.00', expires_at: '2026-11-17T23:59:59Z' }));
    const result = applyUseFirst([b, a], NOW);
    expect(result).toEqual([b, a]);
  });

  it('does not pair rewards across different merchants', () => {
    const a = score(fall);
    const b = score(makeReward({ id: 'b', merchant_id: 'm-nike', merchant_name: 'Nike', code: 'NIKE25', value: '25.00', expires_at: '2026-11-17T23:59:59Z' }));
    const result = applyUseFirst([b, a], NOW);
    expect(result).toEqual([b, a]);
  });
});

describe('saveForLaterLabel', () => {
  it('formats value and short expiry date', () => {
    expect(saveForLaterLabel(score(winter))).toBe('Save for later · 25% off · expires Nov 17');
  });

  it('says "no expiration" for a null expiry', () => {
    const never = score(makeReward({ id: 'b', value: '25.00', expires_at: null }));
    expect(saveForLaterLabel(never)).toBe('Save for later · 25% off · no expiration');
  });
});
