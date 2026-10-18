import merchantsFile from '../../../../shared/seed/seed_merchants.json'
import type { Merchant } from '../types'

const merchants = (merchantsFile as { merchants: Merchant[] }).merchants

const EXTRA_DOMAINS: Record<string, string> = {
  PacSun: 'pacsun.com',
  Aéropostale: 'aeropostale.com',
  'Ulta Card': 'ulta.com',
  'American Express': 'americanexpress.com',
}

export function domainFor(name: string, merchantId?: string | null): string | null {
  const match = merchants.find((merchant) => merchant.id === merchantId || merchant.name === name)
  if (match?.domain) return match.domain
  return EXTRA_DOMAINS[name] ?? null
}
