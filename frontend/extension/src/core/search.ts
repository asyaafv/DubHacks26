/**
 * Seed-data reward search used by the mock fallback (backend unreachable).
 * Mirrors backend/decisions/search: query terms map to MCC groups, results
 * always come from the (seed) user's own rewards, score = value*match*urgency.
 */
import { RewardKind, type Card, type Merchant, type Reward, type SearchChip, type SearchHit } from '../types';
import { daysUntilExpiry, money } from './format';

const RESTAURANTS = ['5812', '5813', '5814'];
const GROCERY = ['5411', '5422', '5441', '5451', '5462', '5921'];
const CLOTHING = ['5611', '5621', '5631', '5641', '5651', '5691', '5699'];
const SHOES = ['5661'];
const ELECTRONICS = ['5045', '5732', '5734'];
const BEAUTY = ['5977', '7230'];
const PHARMACY = ['5122', '5912'];
const HOME = ['5021', '5200', '5211', '5251', '5712', '5713', '5714', '5719'];
const DEPARTMENT = ['5311'];
const FOOD = [...RESTAURANTS, ...GROCERY];
const STREETWEAR = [...CLOTHING, ...SHOES];

function expand(label: string, mccs: string[], terms: string[]): Record<string, { label: string; mccs: string[] }> {
  return Object.fromEntries(terms.map((term) => [term, { label, mccs }]));
}

const KEYWORD_MCCS: Record<string, { label: string; mccs: string[] }> = {
  ...expand('food & dining', FOOD, ['food', 'foods', 'snack', 'hungry']),
  ...expand('restaurants', RESTAURANTS, ['restaurant', 'restaurants', 'dining', 'dinner', 'lunch', 'breakfast', 'meal', 'meals', 'takeout', 'eat', 'eats', 'fast food']),
  ...expand('Mexican food', RESTAURANTS, ['mexican', 'mexican food', 'taco', 'tacos', 'burrito', 'burritos', 'guacamole', 'guac', 'quesadilla']),
  ...expand('pizza & Italian', RESTAURANTS, ['pizza', 'italian', 'pasta']),
  ...expand('fast food', RESTAURANTS, ['burger', 'burgers', 'fries', 'sandwich', 'chicken']),
  ...expand('coffee & cafes', RESTAURANTS, ['coffee', 'latte', 'cafe', 'tea', 'donuts']),
  ...expand('groceries', GROCERY, ['grocery', 'groceries', 'supermarket']),
  ...expand('clothing', CLOTHING, ['clothing', 'clothes', 'apparel', 'fashion', 'outfit', 'shirt', 'pants', 'dress']),
  ...expand("men's clothing", CLOTHING, ['mens', 'men', 'menswear', 'mens clothing']),
  ...expand("women's clothing", CLOTHING, ['womens', 'women', 'womenswear']),
  ...expand('streetwear', STREETWEAR, ['streetwear', 'sneakers', 'sneaker', 'kicks', 'hoodie', 'jeans', 'denim']),
  ...expand('shoes', SHOES, ['shoe', 'shoes', 'footwear', 'boots']),
  ...expand('electronics', ELECTRONICS, ['electronics', 'tech', 'gadgets', 'laptop', 'computer', 'phone', 'tv']),
  ...expand('beauty', BEAUTY, ['beauty', 'makeup', 'cosmetics', 'skincare', 'fragrance']),
  ...expand('pharmacy', PHARMACY, ['pharmacy', 'drugstore', 'medicine', 'vitamins', 'health']),
  ...expand('home & furniture', HOME, ['home', 'furniture', 'sofa', 'couch', 'decor', 'hardware', 'tools']),
  ...expand('department stores', DEPARTMENT, ['department', 'department store', 'department stores']),
};

export const CHIP_DEFINITIONS: Array<{ label: string; query: string; mccs: string[] }> = [
  { label: 'Food', query: 'food', mccs: FOOD },
  { label: 'Clothing', query: 'clothing', mccs: CLOTHING },
  { label: 'Streetwear', query: 'streetwear', mccs: STREETWEAR },
  { label: 'Shoes', query: 'shoes', mccs: SHOES },
  { label: 'Electronics', query: 'electronics', mccs: ELECTRONICS },
  { label: 'Beauty', query: 'beauty', mccs: BEAUTY },
  { label: 'Home', query: 'home', mccs: HOME },
  { label: 'Pharmacy', query: 'pharmacy', mccs: PHARMACY },
  { label: 'Department stores', query: 'department stores', mccs: DEPARTMENT },
];

/** Cuisine/style tags per merchant domain; mirrors the backend merchant tags. */
const MERCHANT_TAGS: Record<string, string[]> = {
  'chipotle.com': ['mexican', 'fast casual'],
  'tacobell.com': ['mexican', 'fast food'],
  'hollisterco.com': ['streetwear', 'casual'],
  'pacsun.com': ['streetwear', 'casual'],
  'aeropostale.com': ['streetwear', 'casual'],
  'nike.com': ['athletic', 'streetwear', 'sneakers'],
  'abercrombie.com': ['casual'],
  'hm.com': ['fast fashion', 'casual'],
  'zara.com': ['fast fashion'],
  'uniqlo.com': ['fast fashion', 'casual'],
  'gap.com': ['casual'],
  'oldnavy.com': ['casual'],
  'starbucks.com': ['coffee'],
  'dunkindonuts.com': ['coffee', 'donuts'],
  'dominos.com': ['pizza', 'italian'],
  'pizzahut.com': ['pizza', 'italian'],
  'papajohns.com': ['pizza', 'italian'],
  'mcdonalds.com': ['burgers', 'fast food'],
  'bk.com': ['burgers', 'fast food'],
  'wendys.com': ['burgers', 'fast food'],
  'subway.com': ['sandwiches', 'fast food'],
  'panerabread.com': ['sandwiches', 'cafe'],
};

/** Query terms that resolve to a merchant tag (the specific match tier). */
const TAG_TERMS: Record<string, string> = {
  mexican: 'mexican',
  taco: 'mexican',
  tacos: 'mexican',
  burrito: 'mexican',
  burritos: 'mexican',
  quesadilla: 'mexican',
  guac: 'mexican',
  guacamole: 'mexican',
  streetwear: 'streetwear',
  'street wear': 'streetwear',
  athletic: 'athletic',
  athleisure: 'athletic',
  sporty: 'athletic',
  sneakers: 'sneakers',
  sneaker: 'sneakers',
  kicks: 'sneakers',
  casual: 'casual',
  coffee: 'coffee',
  latte: 'coffee',
  espresso: 'coffee',
  donuts: 'donuts',
  pizza: 'pizza',
  italian: 'italian',
  burger: 'burgers',
  burgers: 'burgers',
  sandwich: 'sandwiches',
  sandwiches: 'sandwiches',
  'fast food': 'fast food',
  'fast fashion': 'fast fashion',
};

const STOPWORDS = new Set(['a', 'an', 'and', 'any', 'best', 'deals', 'do', 'for', 'have', 'i', 'in', 'me', 'my', 'of', 'offers', 'on', 'reward', 'rewards', 'show', 'store', 'stores', 'the', 'to']);

export function tokenize(text: string): string[] {
  return (text.toLowerCase().match(/[a-z0-9&']+/g) ?? []).filter((t) => !STOPWORDS.has(t));
}

function lexiconMccs(tokens: string[]): Map<string, { term: string; label: string }> {
  const matched = new Map<string, { term: string; label: string }>();
  const terms = [
    ...(tokens.length > 2 ? [tokens.join(' ')] : []),
    ...tokens.slice(0, -1).map((t, i) => `${t} ${tokens[i + 1]}`),
    ...tokens,
  ];
  for (const term of terms) {
    const entry = KEYWORD_MCCS[term];
    if (!entry) continue;
    for (const mcc of entry.mccs) {
      if (!matched.has(mcc)) matched.set(mcc, { term, label: entry.label });
    }
  }
  return matched;
}

function valueComponent(reward: Reward): number {
  const value = money(reward.value);
  if (reward.kind === RewardKind.percent_off) return Math.min(value / 100, 1);
  if (reward.kind === RewardKind.amount_off || reward.kind === RewardKind.cashback) {
    return Math.min(value / 50, 1);
  }
  if (reward.kind === RewardKind.points) return Math.min(value / 500, 1);
  return 0.25;
}

function matchReward(
  reward: Reward,
  merchant: Merchant | undefined,
  tokens: string[],
  mccs: Map<string, { term: string; label: string }>,
): { match: number; reason: string } | null {
  const names = [reward.merchant_name, merchant?.name, ...(merchant?.aliases ?? []).filter((a) => !a.includes('.'))]
    .filter((n): n is string => Boolean(n));
  const text = tokens.join(' ');
  for (const name of names) {
    if (text.includes(name.toLowerCase())) {
      return { match: 1, reason: `Matches your ${reward.merchant_name} reward` };
    }
  }
  const tags = merchant ? MERCHANT_TAGS[merchant.domain] ?? [] : [];
  if (tags.length > 0) {
    const terms = [...tokens.slice(0, -1).map((t, i) => `${t} ${tokens[i + 1]}`), ...tokens];
    for (const term of terms) {
      const tag = TAG_TERMS[term];
      if (tag && tags.includes(tag)) {
        return { match: 0.95, reason: `${reward.merchant_name} is tagged "${tag}" — matches "${term}"` };
      }
    }
  }
  const nameTokens = new Set(names.flatMap((n) => tokenize(n)).filter((t) => t.length > 2));
  for (const token of tokens) {
    if (nameTokens.has(token)) return { match: 0.9, reason: `"${token}" matches ${reward.merchant_name}` };
  }
  const categoryWords = new Set(tokenize(reward.category ?? ''));
  for (const token of tokens) {
    if (categoryWords.has(token)) {
      return { match: 0.85, reason: `${reward.merchant_name} is in ${reward.category} — matches "${token}"` };
    }
  }
  const viaMcc = mccs.get(reward.mcc);
  if (viaMcc) return { match: 0.75, reason: `${reward.category} fits "${viaMcc.term}" (${viaMcc.label})` };
  return null;
}

function bestCard(reward: Reward, cards: Card[]): SearchHit['best_card'] {
  let best: Card | null = null;
  let rate = -1;
  for (const card of cards) {
    let candidate = money(card.base_rate);
    for (const bonus of card.category_rates ?? []) {
      const applies = bonus.mcc_codes?.length
        ? bonus.mcc_codes.includes(reward.mcc)
        : Boolean(bonus.category && bonus.category.toLowerCase() === (reward.category ?? '').toLowerCase());
      if (applies) candidate = Math.max(candidate, money(bonus.rate));
    }
    if (candidate > rate) {
      best = card;
      rate = candidate;
    }
  }
  return best ? { card_id: best.id, name: `${best.issuer} ${best.name}`, rate: String(rate) } : null;
}

function isEligible(reward: Reward, now: Date): boolean {
  if (reward.status !== 'active') return false;
  if (reward.starts_at && new Date(reward.starts_at) > now) return false;
  const days = daysUntilExpiry(reward.expires_at, now);
  return days == null || days >= 0;
}

export function searchSeed(
  query: string,
  rewards: Reward[],
  merchants: Merchant[],
  cards: Card[],
  now: Date = new Date(),
  limit = 8,
): { results: SearchHit[]; totalMatched: number; totalActive: number; secondaryLabel: string | null } {
  const tokens = tokenize(query);
  const mccs = lexiconMccs(tokens);
  const byId = new Map(merchants.map((m) => [m.id, m]));
  const active = rewards.filter((reward) => isEligible(reward, now));
  const hits: SearchHit[] = [];
  for (const reward of active) {
    const found = matchReward(reward, byId.get(reward.merchant_id ?? ''), tokens, mccs);
    if (!found) continue;
    const days = daysUntilExpiry(reward.expires_at, now);
    const urgency = days == null ? 1 : 1 + Math.exp(-days / 3);
    const value = valueComponent(reward);
    hits.push({
      reward,
      score: value * found.match * urgency,
      value_component: value,
      match_component: found.match,
      urgency_component: urgency,
      days_until_expiry: days,
      expiring_soon: days != null && days <= 3,
      reason: found.reason,
      best_card: bestCard(reward, cards),
      secondary: false,
    });
  }
  const byRank = (a: SearchHit, b: SearchHit) => b.score - a.score || b.match_component - a.match_component;
  // Specific hits (merchant name 1.0, tag 0.95, name token 0.9) come first; generic
  // category/MCC matches follow as secondary. Broad queries stay all-primary.
  const specific = hits.filter((hit) => hit.match_component >= 0.9).sort(byRank);
  let ordered = hits.sort(byRank);
  if (specific.length > 0) {
    const generic = hits
      .filter((hit) => hit.match_component < 0.9 && hit.match_component >= 0.75)
      .sort(byRank)
      .map((hit) => ({ ...hit, secondary: true }));
    ordered = [...specific, ...generic];
  }
  const results = ordered.slice(0, limit);
  const secondaryHits = results.filter((hit) => hit.secondary);
  const chip = CHIP_DEFINITIONS.find((entry) =>
    secondaryHits.some((hit) => entry.mccs.includes(hit.reward.mcc)),
  );
  const secondaryLabel = secondaryHits.length > 0 && chip ? `Also in ${chip.label}` : null;
  return { results, totalMatched: ordered.length, totalActive: active.length, secondaryLabel };
}

export function chipsFor(rewards: Reward[], now: Date = new Date()): SearchChip[] {
  const activeMccs = rewards.filter((reward) => isEligible(reward, now)).map((reward) => reward.mcc);
  return CHIP_DEFINITIONS.map(({ label, query, mccs }) => ({
    label,
    query,
    count: activeMccs.filter((mcc) => mccs.includes(mcc)).length,
  })).filter((chip) => chip.count > 0);
}
