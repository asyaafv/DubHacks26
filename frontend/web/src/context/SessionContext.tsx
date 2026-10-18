import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { DEMO_USER, initialUser, storeUser, type SessionUser } from '../util/demo'

type SessionValue = {
  user: SessionUser | null
  enterDemo: () => void
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(() => initialUser())

  const enterDemo = useCallback(() => {
    storeUser(DEMO_USER)
    setUser(DEMO_USER)
  }, [])

  const value = useMemo(() => ({ user, enterDemo }), [user, enterDemo])

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used within SessionProvider')
  return value
}
