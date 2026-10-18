import { describe, expect, it } from 'vitest';
import { chipsFor, searchSeed, tokenize } from './search';
import cardsFile from '../../../../shared/seed/seed_cards.json';
import merchantsFile from '../../../../shared/seed/seed_merchants.json';
import rewardsFile from '../../../../shared/seed/seed_rewards.json';
import type { Card, Merchant, Reward } from '../types';

const DEMO = '00000000-0000-0000-0000-000000000001';
// Mid-demo-window clock: seed rewards expire Oct 19 – Dec 31 2026.
const NOW = new Date('2026-10-18T12:00:00Z');

const rewards = (rewardsFile as { rewards: Reward[] }).rewards.filter((r) => r.user_id === DEMO);
const merchants = (merchantsFile as { merchants: Merchant[] }).merchants;
const cards = (cardsFile as { cards: Card[] }).cards.filter((c) => c.user_id === DEMO);

function names(query: string): string[] {
  return searchSeed(query, rewards, merchants, cards, NOW).results.map((h) => h.reward.merchant_name);
}

describe('searchSeed', () => {
  it('maps "mexican food" to restaurant rewards', () => {
    const found = names('mexican food');
    expect(found).toContain('Taco Bell');
    expect(found).toContain('Chipotle');
    expect(found).not.toContain('Gap');
  });

  it('maps "streetwear" to clothing and shoe rewards', () => {
    const found = names('streetwear');
    expect(found).toContain('Nike');
    expect(found.some((n) => ['Gap', 'Hollister', 'H&M'].includes(n))).toBe(true);
  });

  it('handles broad terms "food" and "clothing"', () => {
    expect(names('food').length).toBeGreaterThanOrEqual(5);
    const clothing = names('clothing');
    expect(clothing).toContain('Gap');
    expect(clothing).not.toContain('Best Buy');
  });

  it('ranks an exact merchant query first with match 1.0', () => {
    const top = searchSeed('hollister rewards', rewards, merchants, cards, NOW).results[0]!;
    expect(top.reward.merchant_name).toBe('Hollister');
    expect(top.match_component).toBe(1);
    expect(top.reward.code).toBe('HCOFALL10');
  });

  it('every hit has a reason, score decomposition and best card', () => {
    const { results } = searchSeed('clothing', rewards, merchants, cards, NOW);
    for (const hit of results) {
      expect(hit.reason.length).toBeGreaterThan(0);
      expect(hit.score).toBeCloseTo(
        hit.value_component * hit.match_component * hit.urgency_component,
        6,
      );
      // US Bank Cash+ pays 5% on MCC 5651 in the demo wallet.
      expect(hit.best_card?.name).toBe('US Bank Cash+ (DEMO)');
    }
  });

  it('excludes used rewards and returns empty for gibberish', () => {
    const { results } = searchSeed('clothing', rewards, merchants, cards, NOW, 20);
    expect(results.map((h) => h.reward.code)).not.toContain('PACSUN25');
    expect(searchSeed('zzgibberishqq', rewards, merchants, cards, NOW).results).toEqual([]);
  });

  it('flags rewards expiring within 3 days', () => {
    const { results } = searchSeed('hollister', rewards, merchants, cards, NOW);
    expect(results[0]!.expiring_soon).toBe(true); // expires Oct 20
  });
});

describe('chipsFor', () => {
  it('builds chips only from categories present in the wallet', () => {
    const chips = chipsFor(rewards, NOW);
    const labels = chips.map((c) => c.label);
    expect(labels).toContain('Food');
    expect(labels).toContain('Streetwear');
    expect(chipsFor([], NOW)).toEqual([]);
  });
});

describe('tokenize', () => {
  it('drops filler words so "stores" alone cannot match everything', () => {
    expect(tokenize('show me my mens clothing rewards')).toEqual(['mens', 'clothing']);
  });
});
