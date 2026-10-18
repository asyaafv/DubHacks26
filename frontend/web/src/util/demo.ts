export const DEMO_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'aamir@lapse.app',
} as const

export type SessionUser = {
  id: string
  email: string
}

const STORAGE_KEY = 'lapse.user'

export function readStoredUser(): SessionUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as SessionUser
    if (!parsed?.id || !parsed?.email) return null
    return parsed
  } catch {
    return null
  }
}

export function storeUser(user: SessionUser): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
}

export function initialUser(): SessionUser | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  if (params.get('demo') === '1') {
    storeUser(DEMO_USER)
    return DEMO_USER
  }
  return readStoredUser()
}
