import { Link, Navigate, useSearchParams } from 'react-router-dom'

export function Landing() {
  const [params] = useSearchParams()
  if (params.get('demo') === '1') return <Navigate to="/dashboard" replace />

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between border-b-2 border-line px-8 py-5">
        <span className="font-display text-3xl font-black uppercase tracking-tight text-tangerine">Lapse</span>
        <Link to="/?demo=1" className="text-xs font-bold text-muted underline">
          Demo
        </Link>
      </header>
      <main className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="text-xs font-black uppercase tracking-[0.18em] text-muted">Placeholder</p>
        <h1 className="mt-3 font-display text-6xl font-black uppercase tracking-tight text-ink">Lapse</h1>
        <p className="mt-4 font-semibold text-muted">Landing page coming soon.</p>
        <Link
          to="/onboarding"
          className="mt-8 inline-flex border-2 border-line bg-tangerine px-5 py-2.5 text-sm font-black uppercase text-white shadow-card"
        >
          Get started
        </Link>
      </main>
    </div>
  )
}
