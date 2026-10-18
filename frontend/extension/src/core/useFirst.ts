import { daysUntilExpiry, formatRewardValue, money } from './format';
import { RewardStatus, type ScoredReward } from '../types';

const DAY_MS = 86_400_000;
/** A must expire within this many days to trigger the rule. */
const USE_FIRST_WINDOW_DAYS = 7;
/** B must outlive A's expiry by at least this many days (or never expire). */
const SAVE_FOR_LATER_GAP_DAYS = 14;

function isActive(scored: ScoredReward): boolean {
  return (scored.reward.status ?? RewardStatus.active) === RewardStatus.active;
}

function daysLeft(scored: ScoredReward, now: Date): number | null {
  return scored.days_until_expiry ?? daysUntilExpiry(scored.reward.expires_at, now);
}

/** Two same-merchant rewards that cannot be combined on one order. */
function cannotCombine(a: ScoredReward, b: ScoredReward): boolean {
  if (a.reward.code && b.reward.code) return true;
  return a.reward.stackable === false || b.reward.stackable === false;
}

function expiryPhrase(days: number): string {
  if (days === 0) return 'today';
  if (days === 1) return 'in 1 day';
  return `in ${days} days`;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** 'Save for later · 25% off · expires Nov 17' (or '· no expiration'). */
export function saveForLaterLabel(scored: ScoredReward): string {
  const value = formatRewardValue(scored.reward);
  const expiry = scored.reward.expires_at ? `expires ${shortDate(scored.reward.expires_at)}` : 'no expiration';
  return `Save for later · ${value} · ${expiry}`;
}

function goodUntilPhrase(scored: ScoredReward): string {
  return scored.reward.expires_at ? `good until ${shortDate(scored.reward.expires_at)}` : 'never expires';
}

/**
 * Mirror of the backend "use it before you lose it" ranking for mock data.
 * Among active same-merchant rewards that cannot combine, when A expires in
 * 0–7 days and B stays usable at least 14 days past A's expiry, A ranks first
 * with use_first + recommendation, and each qualifying B gets save_for_later.
 * Otherwise the input ranking is returned unchanged.
 */
export function applyUseFirst(scored: ScoredReward[], now: Date = new Date()): ScoredReward[] {
  const groups = new Map<string, ScoredReward[]>();
  for (const item of scored) {
    const key = item.reward.merchant_id ?? item.reward.merchant_name;
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  }

  for (const group of groups.values()) {
    const candidates = group
      .filter((item) => {
        if (!isActive(item) || !item.reward.expires_at) return false;
        const days = daysLeft(item, now);
        return days != null && days >= 0 && days <= USE_FIRST_WINDOW_DAYS;
      })
      .sort((a, b) => new Date(a.reward.expires_at!).getTime() - new Date(b.reward.expires_at!).getTime());

    for (const first of candidates) {
      const cutoff = new Date(first.reward.expires_at!).getTime() + SAVE_FOR_LATER_GAP_DAYS * DAY_MS;
      const laters = group.filter((item) => {
        if (item === first || !isActive(item) || !cannotCombine(first, item)) return false;
        return item.reward.expires_at == null || new Date(item.reward.expires_at).getTime() >= cutoff;
      });
      if (laters.length === 0) continue;

      const best = laters.reduce((top, item) => (money(item.reward.value) > money(top.reward.value) ? item : top));
      const days = daysLeft(first, now) ?? 0;
      const flagged = new Map<ScoredReward, ScoredReward>();
      const bestPhrase = best.reward.expires_at
        ? `is ${goodUntilPhrase(best)}`
        : goodUntilPhrase(best);
      flagged.set(first, {
        ...first,
        use_first: true,
        recommendation: `Use first: expires ${expiryPhrase(days)}. Your ${formatRewardValue(best.reward)} ${bestPhrase}.`,
      });
      for (const later of laters) {
        flagged.set(later, {
          ...later,
          save_for_later: true,
          recommendation: `Save for later — ${goodUntilPhrase(later)}`,
        });
      }

      const rest = scored.filter((item) => item !== first).map((item) => flagged.get(item) ?? item);
      return [flagged.get(first)!, ...rest];
    }
  }

  return scored;
}
