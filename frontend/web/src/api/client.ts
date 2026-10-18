import type { SavingsResponse } from './savings'
import type { Reward, SyncResponse } from '../types'

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

/** Mock mode is the default so the UI works with no backend. */
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'

function headers(userId: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-User-Id': userId,
  }
}

async function fail(response: Response): Promise<never> {
  let message = response.statusText || `Request failed (${response.status})`
  try {
    const body = (await response.json()) as { message?: string }
    if (body.message) message = body.message
  } catch {
    // Keep the status text.
  }
  throw new Error(message)
}

export const liveApi = {
  async getSync(userId: string): Promise<SyncResponse> {
    const response = await fetch(`${API_BASE}/sync`, { headers: headers(userId) })
    if (!response.ok) await fail(response)
    return response.json() as Promise<SyncResponse>
  },

  async getSavings(userId: string): Promise<SavingsResponse> {
    const response = await fetch(`${API_BASE}/savings`, { headers: headers(userId) })
    if (!response.ok) await fail(response)
    return response.json() as Promise<SavingsResponse>
  },

  async redeem(userId: string, rewardId: string, saved: string): Promise<Reward> {
    const response = await fetch(`${API_BASE}/rewards/${rewardId}/redeem`, {
      method: 'POST',
      headers: headers(userId),
      body: JSON.stringify({ saved }),
    })
    if (!response.ok) await fail(response)
    return response.json() as Promise<Reward>
  },
}
