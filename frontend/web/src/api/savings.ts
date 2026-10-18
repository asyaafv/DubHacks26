/**
 * Proposed savings contract. Not in shared/types.ts yet — see the PR description.
 *
 * GET /savings
 *   -> { total, items, series }
 * POST /rewards/{id}/redeem
 *   body { saved } -> Reward
 */

export interface SavingsItem {
  reward_id: string
  merchant_name: string
  description: string
  /** Decimal dollars, e.g. "12.00". */
  saved: string
  redeemed_at: string
}

export interface SavingsPoint {
  /** UTC calendar day, YYYY-MM-DD. */
  date: string
  /** Cumulative savings through this day. */
  cumulative: string
}

export interface SavingsResponse {
  total: string
  items: SavingsItem[]
  series: SavingsPoint[]
}

export interface RedeemRequest {
  saved: string
}
