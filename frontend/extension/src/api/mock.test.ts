import { describe, expect, it } from 'vitest';
import { DEMO_USER_ID } from './config';
import { mockLookup, mockStack, mockSync } from './mock';
import { EventType } from '../types';

const NOW = new Date('2026-10-18T12:00:00Z');

describe('mock lookup', () => {
  it('returns the Hollister 10% code for hollisterco.com', () => {
    const result = mockLookup(
      { user_id: DEMO_USER_ID, domain: 'www.hollisterco.com', limit: 3 },
      NOW,
    );
    expect(result.merchant?.name).toBe('Hollister');
    expect(result.merchant?.domain).toBe('hollisterco.com');
    expect(result.rewards).toHaveLength(1);
    expect(result.rewards[0]?.reward.code).toBe('HCOFALL10');
    expect(result.rewards[0]?.reward.kind).toBe('percent_off');
    expect(Number(result.rewards[0]?.reward.value)).toBe(10);
    expect(result.rewards[0]?.days_until_expiry).toBe(2);
  });

  it('returns no rewards for an unknown domain', () => {
    const result = mockLookup({ user_id: DEMO_USER_ID, domain: 'example.com', limit: 3 }, NOW);
    expect(result.merchant).toBeNull();
    expect(result.rewards).toEqual([]);
  });
});

describe('mock stack', () => {
  it('uses the Hollister $500 fixture, including HCOFALL10 and the savings', () => {
    const result = mockStack(
      { user_id: DEMO_USER_ID, domain: 'hollisterco.com', cart_total: '500', items: [] },
      NOW,
    );
    expect(result.chosen_rewards.map((item) => item.reward.code)).toEqual(['HCOFALL10']);
    expect(result.final_price).toBe('450.00');
    expect(result.total_savings).toBe('72.50');
    expect(result.card_cashback).toBe('22.50');
    expect(result.recommended_card?.name).toBe('Cash+ (DEMO)');
    expect(result.recommended_card?.issuer).toBe('US Bank');
    expect(result.explanation).toContain('HCOFALL10');
    expect(result.explanation).toContain('72.50');
  });

  it('applies HCOFALL10 on a non-fixture Hollister cart', () => {
    const result = mockStack(
      { user_id: DEMO_USER_ID, domain: 'hollisterco.com', cart_total: '80.00', items: [] },
      NOW,
    );
    expect(result.chosen_rewards[0]?.reward.code).toBe('HCOFALL10');
    expect(result.final_price).toBe('72.00');
    expect(result.recommended_card?.name).toContain('Freedom Unlimited');
  });
});

describe('mock sync', () => {
  it('includes a reward_added event for the polling fallback', () => {
    const sync = mockSync(undefined, NOW);
    expect(sync.pending_events?.[0]?.event_type).toBe(EventType.reward_added);
    expect(sync.pending_events?.[0]?.data?.code).toBe('HCOFALL10');
    expect(sync.wallet.user_id).toBe(DEMO_USER_ID);
  });
});
