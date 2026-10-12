// Persistent error note — a sealing-wax errata slip, never a vanishing toast.

import { IconX } from './icons'

interface ErrorSlipProps {
  message: string | null
  onDismiss?: () => void
}

export default function ErrorSlip({ message, onDismiss }: ErrorSlipProps) {
  if (!message) {
    return null
  }
  return (
    <div className="slip" role="alert">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <span className="slip-label">Errata</span>
          <p className="mt-0.5 text-sm text-ink-soft">{message}</p>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Descartar error"
            className="rounded p-1 text-linen-500 hover:bg-linen-100 hover:text-ink"
          >
            <IconX className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )
}
