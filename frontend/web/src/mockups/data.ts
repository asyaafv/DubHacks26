/**
 * Design-mockup data layer. Every number rendered in the mockups comes from
 * the same sources the real app uses:
 *  - mockApi.getSync / getSavings  (seeded from shared/seed, same shapes as
 *    GET /sync and GET /savings)
 *  - shared/seed/fixtures/hollister_500_cart.json  (the canonical POST /stack
 *    response for the Hollister $500 cart demo)
 *  - shared/seed/seed_cards.json category_rates    (GET /wallet cards)
 * Nothing is invented here; this file only joins and aggregates.
 */
import { useEffect, useState } from 'react'
import hollisterFixture from '../../../../shared/seed/fixtures/hollister_500_cart.json'
import cardsFile from '../../../../shared/seed/seed_cards.json'
import merchantsFile from '../../../../shared/seed/seed_merchants.json'
import rewardsFile from '../../../../shared/seed/seed_rewards.json'
import { mockApi } from '../api/mock'
import type { SavingsItem, SavingsResponse } from '../api/savings'
import type { Card, Reward, SyncResponse } from '../types'
import { daysUntil } from '../util/dates'
import { DEMO_USER } from '../util/demo'
import { toCents, fromCents } from '../util/money'

export const NOW = new Date('2026-10-18T12:00:00Z')

/* ------------------------------------------------------------------ */
/* /sync + /savings via the app's own mock client                      */
/* ------------------------------------------------------------------ */

export interface MockupData {
  sync: SyncResponse
  savings: SavingsResponse
}

export function useMockupData(): MockupData | null {
  const [data, setData] = useState<MockupData | null>(null)
  useEffect(() => {
    let alive = true
    void Promise.all([mockApi.getSync(DEMO_USER.id), mockApi.getSavings(DEMO_USER.id)]).then(
      ([sync, savings]) => {
        if (alive) setData({ sync, savings })
      },
    )
    return () => {
      alive = false
    }
  }, [])
  return data
}

/* ------------------------------------------------------------------ */
/* Wallet-derived: best cashback card per reward (GET /wallet cards)   */
/* ------------------------------------------------------------------ */

const seedCards = (cardsFile as { cards: Card[] }).cards.filter(
  (card) => card.user_id === DEMO_USER.id,
)

export interface BestCard {
  issuer: string
  name: string
  rate: number
  category: string | null
}

/** Mirrors the backend /stack card pick: best category rate for the MCC, else best base rate. */
export function bestCardFor(mcc: string | undefined | null): BestCard | null {
  let best: BestCard | null = null
  for (const card of seedCards) {
    let rate = Number(card.base_rate)
    let category: string | null = null
    if (mcc) {
      for (const cat of card.category_rates ?? []) {
        if ((cat.mcc_codes ?? []).includes(mcc) && Number(cat.rate) > rate) {
          rate = Number(cat.rate)
          category = cat.category
        }
      }
    }
    if (!best || rate > best.rate) {
      best = { issuer: card.issuer, name: card.name.replace(' (DEMO)', ''), rate, category }
    }
  }
  return best
}

/* ------------------------------------------------------------------ */
/* Savings-derived aggregates (GET /savings items + series)            */
/* ------------------------------------------------------------------ */

function weekKey(iso: string): number {
  const d = new Date(iso)
  const monday = new Date(d)
  const day = (d.getUTCDay() + 6) % 7
  monday.setUTCDate(d.getUTCDate() - day)
  monday.setUTCHours(0, 0, 0, 0)
  return monday.getTime()
}

/** Consecutive calendar weeks (ending at NOW's week or the one before) with >=1 redemption. */
export function savingsStreakWeeks(items: SavingsItem[]): number {
  const weeks = new Set(items.map((item) => weekKey(item.redeemed_at)))
  const WEEK = 7 * 24 * 3600 * 1000
  let cursor = weekKey(NOW.toISOString())
  if (!weeks.has(cursor)) cursor -= WEEK
  let streak = 0
  while (weeks.has(cursor)) {
    streak += 1
    cursor -= WEEK
  }
  return streak
}

export interface MonthTotal {
  label: string
  cents: number
}

export function monthlyTotals(items: SavingsItem[]): MonthTotal[] {
  const map = new Map<string, number>()
  for (const item of items) {
    const key = item.redeemed_at.slice(0, 7)
    map.set(key, (map.get(key) ?? 0) + toCents(item.saved))
  }
  return [...map.entries()].sort().map(([key, cents]) => ({
    label: new Date(`${key}-01T00:00:00Z`).toLocaleDateString('en-US', {
      month: 'short',
      timeZone: 'UTC',
    }),
    cents,
  }))
}

export interface MerchantHistory {
  merchant: string
  count: number
  totalCents: number
  lastDate: string
}

export function merchantHistory(items: SavingsItem[]): MerchantHistory[] {
  const map = new Map<string, MerchantHistory>()
  for (const item of items) {
    const entry = map.get(item.merchant_name) ?? {
      merchant: item.merchant_name,
      count: 0,
      totalCents: 0,
      lastDate: item.redeemed_at,
    }
    entry.count += 1
    entry.totalCents += toCents(item.saved)
    if (item.redeemed_at > entry.lastDate) entry.lastDate = item.redeemed_at
    map.set(item.merchant_name, entry)
  }
  return [...map.values()].sort((a, b) => b.totalCents - a.totalCents)
}

export function centsToDollars(cents: number): string {
  return `$${fromCents(cents)}`
}

/* ------------------------------------------------------------------ */
/* Expiry ring math (rewards[].created_at + expires_at from /sync)     */
/* ------------------------------------------------------------------ */

export interface RingState {
  /** 1 = full window remaining, 0 = lapsed */
  fraction: number
  daysLeft: number | null
  urgency: 'soon' | 'week' | 'later' | 'none'
}

export function ringState(reward: Reward): RingState {
  const days = reward.expires_at ? daysUntil(reward.expires_at, NOW) : null
  if (!reward.expires_at || days === null) return { fraction: 1, daysLeft: null, urgency: 'none' }
  const start = reward.created_at ? new Date(reward.created_at).getTime() : NOW.getTime() - 14 * 86400000
  const end = new Date(reward.expires_at).getTime()
  const span = Math.max(end - start, 1)
  const fraction = Math.min(1, Math.max(0, (end - NOW.getTime()) / span))
  const urgency = days <= 3 ? 'soon' : days <= 7 ? 'week' : 'later'
  return { fraction, daysLeft: days, urgency }
}

/** Open rewards expiring within `days`, soonest first — the "use before it lapses" set. */
export function lapsingSoon(rewards: Reward[], days = 3): Reward[] {
  return rewards
    .filter((reward) => {
      const d = reward.expires_at ? daysUntil(reward.expires_at, NOW) : null
      return d !== null && d >= 0 && d <= days
    })
    .sort((a, b) => (a.expires_at ?? '').localeCompare(b.expires_at ?? ''))
}

export const SOURCE_LABEL: Record<string, string> = {
  email_jsonld: 'Gmail · structured',
  gliner: 'Gmail · AI extract',
  regex: 'Gmail · pattern',
  manual: 'Added manually',
  seed: 'Imported',
}

/* ------------------------------------------------------------------ */
/* Extension popup: /lookup + /stack for the Hollister $500 cart       */
/* ------------------------------------------------------------------ */

interface FixtureShape {
  request: {
    domain: string
    cart_total: string
    items: { name: string; category: string; price: string; quantity: number }[]
  }
  expected_result: {
    chosen_rewards: { reward_id: string; code: string; savings: string; applied_order: number }[]
    recommended_card: { name: string; reason: string }
    card_cashback: string
    original_price: string
    final_price: string
    total_savings: string
    savings_percent: string
    explanation: string
  }
}

const fixture = hollisterFixture as unknown as FixtureShape

const seedRewards = (rewardsFile as { rewards: Reward[] }).rewards
const merchants = (merchantsFile as { merchants: { id: string; name: string; domain: string; mcc: string; category: string }[] }).merchants

export interface PopupStack {
  merchant: { name: string; domain: string; mcc: string; category: string }
  cartTotal: string
  items: FixtureShape['request']['items']
  reward: Reward
  rewardSavings: string
  card: BestCard
  cardReason: string
  cardCashback: string
  originalPrice: string
  finalPrice: string
  totalSavings: string
  savingsPercent: string
  explanation: string
  /** Mirrors the extension's mock /events reward_added payload. */
  toast: { merchant: string; label: string; code: string }
}

export function hollisterPopup(): PopupStack {
  const merchant = merchants.find((m) => m.domain === fixture.request.domain)!
  const chosen = fixture.expected_result.chosen_rewards[0]
  const reward = seedRewards.find((r) => r.id === chosen.reward_id)!
  const card = bestCardFor(merchant.mcc)!
  return {
    merchant,
    cartTotal: fixture.request.cart_total,
    items: fixture.request.items,
    reward,
    rewardSavings: chosen.savings,
    card,
    cardReason: fixture.expected_result.recommended_card.reason,
    cardCashback: fixture.expected_result.card_cashback,
    originalPrice: fixture.expected_result.original_price,
    finalPrice: fixture.expected_result.final_price,
    totalSavings: fixture.expected_result.total_savings,
    savingsPercent: fixture.expected_result.savings_percent,
    explanation: fixture.expected_result.explanation,
    toast: { merchant: 'Hollister', label: '10% off', code: 'HCOFALL10' },
  }
}
