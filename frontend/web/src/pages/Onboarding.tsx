import { Link } from 'react-router-dom'

export function Onboarding() {
  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between px-8 py-5">
        <Link to="/" className="font-serif text-3xl text-accent">
          Lapse
        </Link>
        <Link to="/?demo=1" className="text-xs text-muted underline">
          Demo
        </Link>
      </header>
      <main className="mx-auto max-w-lg px-6 py-24">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted">Placeholder</p>
        <h1 className="mt-3 font-serif text-5xl text-ink">Onboarding</h1>
        <p className="mt-4 text-muted">Onboarding coming soon.</p>
        <Link to="/" className="mt-8 inline-flex text-sm font-semibold text-accent">
          ← Back
        </Link>
      </main>
    </div>
  )
}
