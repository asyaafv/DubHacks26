import { liveApi, USE_MOCKS } from './client'
import { mockApi } from './mock'
import type { SavingsResponse } from './savings'
import type { Reward, SyncResponse } from '../types'

export { API_BASE, USE_MOCKS } from './client'

const backend = USE_MOCKS ? mockApi : liveApi

export const api = {
  getSync(userId: string): Promise<SyncResponse> {
    return backend.getSync(userId)
  },
  getSavings(userId: string): Promise<SavingsResponse> {
    return backend.getSavings(userId)
  },
  redeem(userId: string, rewardId: string, saved: string): Promise<Reward> {
    return backend.redeem(userId, rewardId, saved)
  },
}
