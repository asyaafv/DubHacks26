import { liveApi, USE_MOCKS } from './client'
import { mockApi } from './mock'
import type { SavingsResponse } from './savings'
import type { Reward, SyncResponse } from '../types'

export { API_BASE, USE_MOCKS } from './client'

export type DataSource = 'live' | 'mock'

// Sticky per-session: once the backend proves unreachable we stay on mock data
// so the UI never mixes live and demo state mid-session.
let usingMocks = USE_MOCKS

export function getDataSource(): DataSource {
  return usingMocks ? 'mock' : 'live'
}

/** fetch() rejects with a TypeError when the backend cannot be reached at all. */
function isUnreachable(error: unknown): boolean {
  return error instanceof TypeError
}

async function withFallback<T>(live: () => Promise<T>, mock: () => Promise<T>): Promise<T> {
  if (usingMocks) return mock()
  try {
    return await live()
  } catch (error) {
    if (!isUnreachable(error)) throw error
    usingMocks = true
    console.warn('Lapse API unreachable; falling back to built-in demo data.', error)
    return mock()
  }
}

export const api = {
  getSync(userId: string): Promise<SyncResponse> {
    return withFallback(
      () => liveApi.getSync(userId),
      () => mockApi.getSync(userId),
    )
  },
  getSavings(userId: string): Promise<SavingsResponse> {
    return withFallback(
      () => liveApi.getSavings(userId),
      () => mockApi.getSavings(userId),
    )
  },
  redeem(userId: string, rewardId: string, saved: string): Promise<Reward> {
    return withFallback(
      () => liveApi.redeem(userId, rewardId, saved),
      () => mockApi.redeem(userId, rewardId, saved),
    )
  },
}
