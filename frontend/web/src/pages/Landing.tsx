import { Link, Navigate, useSearchParams } from 'react-router-dom'

export function Landing() {
  const [params] = useSearchParams()
  if (params.get('demo') === '1') return <Navigate to="/dashboard" replace />

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-5">
        <span className="font-serif text-3xl text-accent">Lapse</span>
        <Link to="/?demo=1" className="text-xs text-muted underline">
          Demo
        </Link>
      </header>
      <main className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">Placeholder</p>
        <h1 className="mt-3 font-serif text-6xl text-ink">Lapse</h1>
        <p className="mt-4 text-muted">Landing page coming soon.</p>
        <Link
          to="/onboarding"
          className="mt-8 inline-flex rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-white"
        >
          Get started
        </Link>
      </main>
    </div>
  )
}
