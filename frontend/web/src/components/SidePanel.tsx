import { useEffect, type ReactNode } from 'react'

export function SidePanel({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 bg-ink/40"
        aria-label="Close details"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="details-title"
        className="absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l-2 border-line bg-paper"
      >
        <div className="flex items-center justify-between border-b-2 border-line bg-amber px-6 py-4">
          <h2 id="details-title" className="font-display text-sm font-black uppercase tracking-[0.14em] text-ink">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="border-2 border-line bg-white px-2 py-1 text-xs font-black uppercase text-ink shadow-card"
          >
            Close
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </aside>
    </div>
  )
}
