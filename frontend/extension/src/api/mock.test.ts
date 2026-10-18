import { describe, expect, it } from 'vitest';
import { DEMO_USER_ID } from './config';
import { mockLookup, mockStack, mockSync } from './mock';
import { applyUseFirst } from '../core/useFirst';
import { EventType, RewardKind, RewardSource, RewardStatus, type ScoredReward } from '../types';

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

  it('puts HCOFALL10 first with use_first when a longer-lived 25% code joins the list', () => {
    // mockLookup reads the static seed JSON (one active Hollister reward), so
    // test the applyUseFirst composition directly with an injected
    // HCOWINTER25-style reward on top of the real scored lookup output.
    const lookup = mockLookup({ user_id: DEMO_USER_ID, domain: 'www.hollisterco.com', limit: 3 }, NOW);
    const fall = lookup.rewards.find((scored) => scored.reward.code === 'HCOFALL10');
    expect(fall).toBeDefined();

    const winter: ScoredReward = {
      reward: {
        ...fall!.reward,
        id: '22222222-2222-2222-2222-222222222299',
        kind: RewardKind.percent_off,
        value: '25.00',
        code: 'HCOWINTER25',
        stackable: false,
        expires_at: '2026-11-17T23:59:59Z',
        source: RewardSource.seed,
        status: RewardStatus.active,
      },
      score: 0.99,
      value_component: 0.5,
      match_component: 1,
      urgency_component: 1,
      days_until_expiry: 30,
    };

    // Winter scores higher, so it leads the pre-rule ranking.
    const ranked = applyUseFirst([winter, fall!], NOW);
    expect(ranked.map((scored) => scored.reward.code)).toEqual(['HCOFALL10', 'HCOWINTER25']);
    expect(ranked[0]?.use_first).toBe(true);
    expect(ranked[0]?.recommendation).toBe(
      'Use first: expires in 2 days. Your 25% off is good until Nov 17.',
    );
    expect(ranked[1]?.save_for_later).toBe(true);
    expect(ranked[1]?.recommendation).toBe('Save for later — good until Nov 17');
  });

  it('returns no rewards for an unknown domain', () => {
    const result = mockLookup({ user_id: DEMO_USER_ID, domain: 'example.com', limit: 3 }, NOW);
    expect(result.merchant).toBeNull();
    expect(result.rewards).toEqual([]);
  });

  it('returns every direct Starbucks reward even though both score low', () => {
    const result = mockLookup({ user_id: DEMO_USER_ID, domain: 'starbucks.com', limit: 10 }, NOW);
    expect(result.merchant?.name).toBe('Starbucks');
    expect(result.rewards.map((s) => s.reward.kind).sort()).toEqual(['bogo', 'points']);
    expect(result.rewards.every((s) => s.match_component === 1)).toBe(true);
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
    // main's seed gives US Bank Cash+ 5% on MCC 5651, so it beats Freedom Unlimited.
    expect(result.recommended_card?.name).toContain('Cash+');
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
