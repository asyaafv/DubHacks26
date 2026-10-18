import type { ToastRecord } from '../core/messages';

export function ToastBanner({ toast, onDismiss }: { toast: ToastRecord; onDismiss: () => void }) {
  return (
    <div
      className="flex rotate-[-0.5deg] items-start justify-between gap-2 border-2 border-ink bg-lime px-3 py-1.5 text-[11px] font-black uppercase text-ink shadow-card"
      data-testid="toast"
      role="status"
    >
      <p>✉ {toast.message}</p>
      <button
        type="button"
        className="shrink-0 text-[10px] font-black uppercase underline decoration-2 underline-offset-2"
        onClick={onDismiss}
      >
        Dismiss
      </button>
    </div>
  );
}
