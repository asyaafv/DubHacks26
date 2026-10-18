import { Link } from 'react-router-dom'

export function Onboarding() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between border-b-2 border-line px-8 py-5">
        <Link to="/" className="font-display text-3xl font-black uppercase tracking-tight text-tangerine">
          Lapse
        </Link>
        <Link to="/?demo=1" className="text-xs font-bold text-muted underline">
          Demo
        </Link>
      </header>
      <main className="mx-auto max-w-lg px-6 py-24">
        <p className="text-xs font-black uppercase tracking-[0.18em] text-muted">Placeholder</p>
        <h1 className="mt-3 font-display text-5xl font-black uppercase tracking-tight text-ink">Onboarding</h1>
        <p className="mt-4 font-semibold text-muted">Onboarding coming soon.</p>
        <Link
          to="/"
          className="mt-8 inline-flex border-2 border-line bg-white px-3 py-1 text-xs font-black uppercase text-ink shadow-card"
        >
          ← Back
        </Link>
      </main>
    </div>
  )
}
