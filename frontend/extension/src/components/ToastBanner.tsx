import type { ToastRecord } from '../core/messages';

export function ToastBanner({ toast, onDismiss }: { toast: ToastRecord; onDismiss: () => void }) {
  return (
    <div
      className="flex items-start justify-between gap-2 rounded-xl bg-white px-3 py-2 text-sm shadow-sm ring-1 ring-lapse/20"
      data-testid="toast"
      role="status"
    >
      <p>{toast.message}</p>
      <button type="button" className="text-xs text-stone-500" onClick={onDismiss}>
        Dismiss
      </button>
    </div>
  );
}
