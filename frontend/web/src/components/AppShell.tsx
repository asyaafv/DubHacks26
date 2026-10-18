import { Link, Outlet } from 'react-router-dom'
import { useSession } from '../context/SessionContext'

export function AppShell() {
  const { user } = useSession()

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link to="/dashboard" className="font-serif text-3xl tracking-tight text-accent">
            Lapse
          </Link>
          {user ? <span className="text-sm text-muted">{user.email}</span> : null}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
