import { RewardKind, type Reward } from '../types';

export function money(value: number | string | null | undefined): number {
  if (value == null || value === '') return 0;
  const amount = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

export function moneyString(value: number): string {
  return value.toFixed(2);
}

export function formatMoney(value: number | string): string {
  return money(value).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function trimNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

export function formatRewardValue(reward: Reward): string {
  const amount = money(reward.value);
  switch (reward.kind) {
    case RewardKind.percent_off:
      return `${trimNumber(amount)}% off`;
    case RewardKind.amount_off:
      return `${formatMoney(amount)} off`;
    case RewardKind.points:
      return `${trimNumber(amount)} points`;
    case RewardKind.free_item:
      return 'Free item';
    case RewardKind.bogo:
      return 'Buy one, get one';
    case RewardKind.cashback:
      return `${formatMoney(amount)} cashback`;
    default:
      return trimNumber(amount);
  }
}

/** Whole days until expiry, matching the backend stub's `timedelta.days` floor. */
export function daysUntilExpiry(
  expiresAt: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!expiresAt) return null;
  const expiry = new Date(expiresAt);
  if (Number.isNaN(expiry.getTime())) return null;
  const ms = expiry.getTime() - now.getTime();
  if (ms < 0) return -1;
  return Math.floor(ms / 86_400_000);
}

export function formatExpiry(days: number | null | undefined): string | null {
  if (days == null) return null;
  if (days < 0) return 'Expired';
  if (days === 0) return 'Expires today';
  if (days === 1) return 'Expires in 1 day';
  return `Expires in ${days} days`;
}

export function isExpiringSoon(days: number | null | undefined): boolean {
  return days != null && days >= 0 && days <= 3;
}
