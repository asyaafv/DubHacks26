import { useEffect, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { RewardsProvider } from './context/RewardsContext'
import { SessionProvider, useSession } from './context/SessionContext'
import { CalendarPage } from './pages/CalendarPage'
import { Dashboard } from './pages/Dashboard'
import { Landing } from './pages/Landing'
import { Onboarding } from './pages/Onboarding'
import { Savings } from './pages/Savings'

function DemoRedirect() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { enterDemo } = useSession()

  useEffect(() => {
    if (params.get('demo') !== '1') return
    enterDemo()
    if (location.pathname !== '/dashboard' || location.search) {
      navigate('/dashboard', { replace: true })
    }
  }, [params, location.pathname, location.search, enterDemo, navigate])

  return null
}

function RequireUser({ children }: { children: ReactNode }) {
  const { user } = useSession()
  if (!user) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <DemoRedirect />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/onboarding" element={<Onboarding />} />
          <Route
            element={
              <RequireUser>
                <RewardsProvider>
                  <AppShell />
                </RewardsProvider>
              </RequireUser>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/savings" element={<Savings />} />
            <Route path="/calendar" element={<CalendarPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  )
}
