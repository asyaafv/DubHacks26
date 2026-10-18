import hollisterFixtureJson from '../../../../shared/seed/fixtures/hollister_500_cart.json';
import cardsFile from '../../../../shared/seed/seed_cards.json';
import membershipsFile from '../../../../shared/seed/seed_memberships.json';
import merchantsFile from '../../../../shared/seed/seed_merchants.json';
import rewardsFile from '../../../../shared/seed/seed_rewards.json';
import { DEMO_USER_ID } from './config';
import { daysUntilExpiry, formatRewardValue, money, moneyString } from '../core/format';
import { normalizeDomain } from '../core/page';
import {
  CardNetwork,
  EventType,
  RewardKind,
  RewardSource,
  RewardStatus,
  type Card,
  type CartItem,
  type ChosenReward,
  type Event,
  type LookupRequest,
  type LookupResult,
  type Membership,
  type Merchant,
  type Reward,
  type ScoredReward,
  type StackRequest,
  type StackResult,
  type SyncResponse,
  type Wallet,
} from '../types';

interface SeedReward extends Omit<Reward, 'kind' | 'source' | 'status'> {
  kind: string;
  source: string;
  status?: string;
}

interface FixtureFile {
  request: {
    domain?: string;
    cart_total?: string | number;
    user_id?: string;
  };
  expected_result: {
    chosen_rewards: Array<{
      reward_id: string;
      savings: string;
      applied_order: number;
    }>;
    recommended_card?: { name?: string };
    card_cashback: string;
    original_price: string;
    final_price: string;
    total_savings: string;
    savings_percent: string;
    explanation: string;
  };
}

const rewards = (rewardsFile as { rewards: SeedReward[] }).rewards;
const merchants = (merchantsFile as { merchants: Merchant[] }).merchants;
const cards = (cardsFile as { cards: Card[] }).cards;
const memberships = (membershipsFile as { memberships: Membership[] }).memberships;
const hollisterFixture = hollisterFixtureJson as FixtureFile;

function toReward(raw: SeedReward): Reward {
  return {
    ...raw,
    kind: raw.kind as RewardKind,
    source: raw.source as RewardSource,
    status: (raw.status as RewardStatus | undefined) ?? RewardStatus.active,
  };
}

function toCard(raw: Card): Card {
  return {
    ...raw,
    network: raw.network as CardNetwork,
    category_rates: raw.category_rates ?? [],
  };
}

function allRewards(): Reward[] {
  return rewards.filter((reward) => reward.user_id === DEMO_USER_ID).map(toReward);
}

function allCards(): Card[] {
  return cards.filter((card) => card.user_id === DEMO_USER_ID).map(toCard);
}

function isUsable(reward: Reward, now: Date): boolean {
  if ((reward.status ?? RewardStatus.active) !== RewardStatus.active) return false;
  const days = daysUntilExpiry(reward.expires_at, now);
  return days == null || days >= 0;
}

function findMerchant(domainOrId: { domain?: string | null; merchantId?: string | null }): Merchant | null {
  if (domainOrId.merchantId) {
    const byId = merchants.find((merchant) => merchant.id === domainOrId.merchantId);
    if (byId) return byId;
  }
  if (!domainOrId.domain) return null;
  const normalized = normalizeDomain(domainOrId.domain);
  return (
    merchants.find((merchant) => {
      const names = [merchant.domain, ...(merchant.aliases ?? [])];
      return names.some((alias) => normalizeDomain(alias) === normalized);
    }) ?? null
  );
}

function valueUsd(reward: Reward): number {
  if (reward.kind === RewardKind.percent_off) return money(reward.value);
  if (reward.kind === RewardKind.amount_off || reward.kind === RewardKind.cashback) {
    return money(reward.value);
  }
  return 5;
}

function scoreReward(reward: Reward, merchant: Merchant | null, now: Date): ScoredReward {
  const valueComponent = Math.min(valueUsd(reward) / 50, 1);
  let matchComponent = 0.5;
  if (merchant && reward.merchant_id === merchant.id) matchComponent = 1;
  else if (merchant && reward.category === merchant.category) matchComponent = 0.7;

  const days = daysUntilExpiry(reward.expires_at, now);
  const urgencyComponent = days == null || days < 0 ? 1 : 1 + Math.exp(-days / 3);
  return {
    reward,
    score: valueComponent * matchComponent * urgencyComponent,
    value_component: valueComponent,
    match_component: matchComponent,
    urgency_component: urgencyComponent,
    days_until_expiry: days != null && days >= 0 ? days : days === -1 ? 0 : null,
  };
}

export function mockLookup(request: LookupRequest, now: Date = new Date()): LookupResult {
  const userId = request.user_id || DEMO_USER_ID;
  const merchant = findMerchant({ domain: request.domain, merchantId: request.merchant_id });
  const usable = allRewards().filter((reward) => reward.user_id === userId && isUsable(reward, now));
  const scored = usable
    .map((reward) => scoreReward(reward, merchant, now))
    .filter((item) => (merchant ? item.match_component === 1 : false))
    .sort((a, b) => b.score - a.score);
  const limit = request.limit ?? 3;
  return {
    merchant,
    rewards: scored.slice(0, Math.max(0, limit)),
    total_available: usable.length,
  };
}

function rewardSavings(reward: Reward, cart: number): number {
  let savings = 0;
  if (reward.kind === RewardKind.percent_off) savings = (cart * money(reward.value)) / 100;
  else if (reward.kind === RewardKind.amount_off) savings = money(reward.value);
  const cap = reward.max_discount == null ? Number.POSITIVE_INFINITY : money(reward.max_discount);
  return Math.max(0, Math.min(savings, cap, cart));
}

function blockedByExclusions(reward: Reward, items: CartItem[]): boolean {
  if (!reward.exclusions?.length || items.length === 0) return false;
  return items.every((item) => {
    const name = item.name.toLowerCase();
    const category = (item.category ?? '').toLowerCase();
    return reward.exclusions!.some((exclusion) => {
      const blocked = exclusion.toLowerCase();
      return name.includes(blocked) || category === blocked;
    });
  });
}

function applicableRewards(domain: string, cart: number, items: CartItem[], now: Date): Reward[] {
  const merchant = findMerchant({ domain });
  if (!merchant) return [];
  return allRewards().filter((reward) => {
    if (reward.merchant_id !== merchant.id || !isUsable(reward, now)) return false;
    if (reward.min_spend != null && cart < money(reward.min_spend)) return false;
    if (blockedByExclusions(reward, items)) return false;
    return true;
  });
}

function bestCombo(options: Reward[], cart: number): Reward[] {
  let best: Reward[] = [];
  let bestSavings = 0;
  const consider = (combo: Reward[]) => {
    const savings = Math.min(
      cart,
      combo.reduce((sum, reward) => sum + rewardSavings(reward, cart), 0),
    );
    if (savings > bestSavings + 1e-9) {
      best = combo;
      bestSavings = savings;
    }
  };

  const stackableWithoutCode = options.filter((reward) => reward.stackable && !reward.code);
  if (stackableWithoutCode.length > 0) consider(stackableWithoutCode);

  for (const reward of options) {
    consider([reward]);
    if (reward.stackable) {
      const others = stackableWithoutCode.filter((other) => other.id !== reward.id);
      consider([reward, ...others]);
    }
  }
  return best;
}

function rateFor(card: Card, mcc: string | undefined): number {
  if (mcc) {
    for (const rate of card.category_rates ?? []) {
      if ((rate.mcc_codes ?? []).includes(mcc)) return money(rate.rate);
    }
  }
  return money(card.base_rate);
}

function bestCard(mcc: string | undefined): { card: Card | null; rate: number } {
  let card: Card | null = null;
  let rate = -1;
  for (const candidate of allCards()) {
    const candidateRate = rateFor(candidate, mcc);
    if (candidateRate > rate) {
      card = candidate;
      rate = candidateRate;
    }
  }
  return { card, rate: Math.max(0, rate) };
}

function findCardByLabel(label: string): Card | null {
  const needle = label.toLowerCase();
  return (
    allCards().find((card) => `${card.issuer} ${card.name}`.toLowerCase() === needle) ??
    allCards().find((card) => needle.includes(card.name.toLowerCase())) ??
    null
  );
}

function fromFixture(request: StackRequest, cart: number, now: Date): StackResult | null {
  const fixture = hollisterFixture;
  if (fixture.request.user_id && request.user_id && fixture.request.user_id !== request.user_id) {
    return null;
  }
  if (normalizeDomain(fixture.request.domain ?? '') !== normalizeDomain(request.domain ?? '')) return null;
  if (Math.abs(money(fixture.request.cart_total) - cart) >= 0.001) return null;

  const expected = fixture.expected_result;
  const catalog = allRewards().filter((reward) => isUsable(reward, now));
  const chosen: ChosenReward[] = [];
  for (const item of expected.chosen_rewards) {
    const reward = catalog.find((candidate) => candidate.id === item.reward_id);
    if (!reward) return null;
    chosen.push({
      reward_id: reward.id,
      reward,
      savings: item.savings,
      applied_order: item.applied_order,
    });
  }
  const recommended = expected.recommended_card?.name
    ? findCardByLabel(expected.recommended_card.name)
    : null;
  if (expected.recommended_card?.name && !recommended) return null;

  return {
    chosen_rewards: chosen,
    recommended_card: recommended,
    card_cashback: expected.card_cashback,
    original_price: expected.original_price,
    final_price: expected.final_price,
    total_savings: expected.total_savings,
    savings_percent: expected.savings_percent,
    explanation: expected.explanation,
    alternatives: [],
    solver_status: 'mock',
  };
}

function explain(chosen: ChosenReward[], card: Card | null, cashback: number, total: number): string {
  const parts: string[] = [];
  for (const item of chosen) {
    const label = formatRewardValue(item.reward);
    const savings = moneyString(money(item.savings));
    parts.push(
      item.reward.code
        ? `Applied ${item.reward.code} for ${label} (${savings} savings)`
        : `Applied ${label} (${savings} savings)`,
    );
  }
  if (card && cashback > 0) {
    parts.push(`Use ${card.issuer} ${card.name} for ${moneyString(cashback)} cashback`);
  }
  if (parts.length === 0) return 'No rewards or card cashback apply to this cart.';
  return `${parts.join('. ')}. Total savings: $${moneyString(total)}`;
}

export function mockStack(request: StackRequest, now: Date = new Date()): StackResult {
  const cart = money(request.cart_total);
  const fixture = fromFixture(request, cart, now);
  if (fixture) return fixture;

  const merchant = findMerchant({ domain: request.domain, merchantId: request.merchant_id });
  const chosenRewards = cart > 0 ? bestCombo(applicableRewards(request.domain ?? '', cart, request.items ?? [], now), cart) : [];
  const chosen: ChosenReward[] = chosenRewards.map((reward, index) => ({
    reward_id: reward.id,
    reward,
    savings: moneyString(rewardSavings(reward, cart)),
    applied_order: index + 1,
  }));
  const rewardSavingsTotal = chosen.reduce((sum, item) => sum + money(item.savings), 0);
  const priceAfterRewards = Math.max(0, cart - rewardSavingsTotal);
  const { card, rate } = bestCard(merchant?.mcc);
  const cashback = priceAfterRewards * (rate / 100);
  const totalSavings = rewardSavingsTotal + cashback;
  return {
    chosen_rewards: chosen,
    recommended_card: card,
    card_cashback: moneyString(cashback),
    original_price: moneyString(cart),
    final_price: moneyString(priceAfterRewards),
    total_savings: moneyString(totalSavings),
    savings_percent: moneyString(cart > 0 ? (totalSavings / cart) * 100 : 0),
    explanation: explain(chosen, card, cashback, totalSavings),
    alternatives: [],
    solver_status: 'mock',
  };
}

export function mockRewardAddedEvent(): Event {
  return {
    event_type: EventType.reward_added,
    timestamp: '2026-10-18T12:00:00Z',
    user_id: DEMO_USER_ID,
    reward_id: '22222222-2222-2222-2222-222222222201',
    data: {
      merchant_name: 'Hollister',
      code: 'HCOFALL10',
      label: '10% off',
    },
  };
}

/** Live events send kind + value (e.g. percent_off / "10"); mocks send a prebuilt label. */
function eventLabel(data: Record<string, unknown>): string {
  if (typeof data.label === 'string') return data.label;
  const kind = typeof data.kind === 'string' ? data.kind : '';
  const value = typeof data.value === 'string' || typeof data.value === 'number' ? String(data.value) : '';
  if (!kind) return '';
  switch (kind) {
    case RewardKind.percent_off:
      return value ? `${money(value)}% off` : 'Percent off';
    case RewardKind.amount_off:
      return value ? `$${moneyString(money(value))} off` : 'Amount off';
    case RewardKind.cashback:
      return value ? `$${moneyString(money(value))} cashback` : 'Cashback';
    case RewardKind.points:
      return value ? `${money(value)} points` : 'Points';
    case RewardKind.free_item:
      return 'Free item';
    case RewardKind.bogo:
      return 'Buy one, get one';
    default:
      return value;
  }
}

export function toastMessage(event: Event): string | null {
  if (event.event_type !== EventType.reward_added) return null;
  const data = event.data ?? {};
  const merchant = typeof data.merchant_name === 'string' ? data.merchant_name : '';
  const label = eventLabel(data);
  const code = typeof data.code === 'string' ? data.code : '';
  if (!merchant && !label && !code) return 'New reward added';
  const detail = [merchant, label].filter(Boolean).join(' ');
  return code ? `New reward added · ${detail} · ${code}` : `New reward added · ${detail}`;
}

/** Mock fallback for POST /rewards/{id}/redeem: returns the seed reward marked used. */
export function mockRedeem(rewardId: string): Reward {
  const reward = allRewards().find((candidate) => candidate.id === rewardId);
  if (!reward) throw new Error(`Reward ${rewardId} not found`);
  return { ...reward, status: RewardStatus.used };
}

export function mockWallet(now: Date = new Date()): Wallet {
  const usable = allRewards().filter((reward) => isUsable(reward, now));
  const expiringSoon = usable.filter((reward) => {
    const days = daysUntilExpiry(reward.expires_at, now);
    return days != null && days <= 3;
  }).length;
  return {
    user_id: DEMO_USER_ID,
    cards: allCards(),
    memberships,
    active_rewards_count: usable.length,
    expiring_soon_count: expiringSoon,
  };
}

export function mockSync(since?: string, now: Date = new Date()): SyncResponse {
  void since;
  return {
    user_id: DEMO_USER_ID,
    rewards: allRewards().filter((reward) => isUsable(reward, now)),
    wallet: mockWallet(now),
    last_sync: now.toISOString(),
    pending_events: [mockRewardAddedEvent()],
  };
}
