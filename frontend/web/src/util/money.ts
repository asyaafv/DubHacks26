import type { SavingsItem, SavingsPoint } from '../api/savings'

export function toCents(value: string | number): number {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100)
}

export function fromCents(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}

export function formatDollars(value: string | number): string {
  const cents = toCents(value)
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  const dollars = Math.floor(abs / 100).toLocaleString('en-US')
  return `${sign}$${dollars}.${String(abs % 100).padStart(2, '0')}`
}

export function sumSaved(items: SavingsItem[]): string {
  const cents = items.reduce((sum, item) => sum + toCents(item.saved), 0)
  return fromCents(cents)
}

/** One burn-up point per UTC redemption day, sorted ascending. */
export function buildSeries(items: SavingsItem[]): SavingsPoint[] {
  const byDate = new Map<string, number>()
  for (const item of items) {
    const day = item.redeemed_at.slice(0, 10)
    byDate.set(day, (byDate.get(day) ?? 0) + toCents(item.saved))
  }
  let running = 0
  return [...byDate.keys()].sort().map((date) => {
    running += byDate.get(date) ?? 0
    return { date, cumulative: fromCents(running) }
  })
}
