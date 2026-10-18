export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

/** Monday-start week containing `date`. */
export function startOfWeek(date: Date): Date {
  const day = startOfDay(date)
  const weekday = day.getDay()
  const diff = weekday === 0 ? -6 : 1 - weekday
  return addDays(day, diff)
}

export function dateKey(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function localDay(iso: string): string {
  return dateKey(new Date(iso))
}

export function daysUntil(iso: string | null | undefined, now = new Date()): number | null {
  if (!iso) return null
  const exp = new Date(iso)
  const start = startOfDay(now).getTime()
  const end = startOfDay(exp).getTime()
  return Math.round((end - start) / 86_400_000)
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'No date'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatMonthDay(isoDate: string): string {
  const [y, m, d] = isoDate.split('-').map(Number)
  if (!y || !m || !d) return isoDate
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'UTC',
  })
}

export function weekdayLabels(): string[] {
  return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
}

export function monthGrid(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const gridStart = startOfWeek(first)
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index))
}

export function weekDays(anchor: Date): Date[] {
  const start = startOfWeek(anchor)
  return Array.from({ length: 7 }, (_, index) => addDays(start, index))
}

export function sameDay(a: Date, b: Date): boolean {
  return dateKey(a) === dateKey(b)
}

export type Urgency = 'soon' | 'week' | 'later' | 'none'

export function urgencyFor(days: number | null): Urgency {
  if (days === null) return 'none'
  if (days <= 2) return 'soon'
  if (days <= 7) return 'week'
  return 'later'
}
