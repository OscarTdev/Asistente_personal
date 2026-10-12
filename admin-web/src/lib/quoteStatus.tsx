// Quote status labels and badge styles (single source of truth).

export const QUOTE_STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  sent: 'Enviada',
  accepted: 'Aceptada',
  rejected: 'Rechazada',
  expired: 'Vencida',
}

export const QUOTE_STATUSES = ['draft', 'sent', 'accepted', 'rejected', 'expired']

function statusClasses(status: string): string {
  switch (status) {
    case 'draft':
      return 'bg-linen-100 text-linen-600'
    case 'sent':
      return 'bg-petrol-wash text-petrol'
    case 'accepted':
      return 'bg-ok-wash text-ok'
    case 'rejected':
      return 'bg-lacre-wash text-lacre'
    case 'expired':
      return 'bg-brass-wash text-brass-ink'
    default:
      return 'bg-linen-100 text-linen-600'
  }
}

export function QuoteStatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusClasses(status)}`}>
      {QUOTE_STATUS_LABELS[status] ?? status}
    </span>
  )
}
