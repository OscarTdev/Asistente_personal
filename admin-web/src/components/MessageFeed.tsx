import { FeedEvent } from '../types'

export function MessageFeed({ events }: { events: FeedEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm font-medium text-ink">Sin mensajes todavía</p>
        <p className="mt-1 text-xs text-linen-600">
          Cuando un cliente escriba al WhatsApp conectado, su ficha aparecerá aquí en tiempo real.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {events.map((event) => (
        <article key={event.id} className="ficha px-4 py-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-sm font-semibold text-ink">
              {event.data.contact_wa_id ?? 'Desconocido'}
            </span>
            <time className="tabular shrink-0 text-xs text-linen-600">
              {new Date(event.created_at).toLocaleTimeString('es-CO', { hour12: false })}
            </time>
          </div>
          {event.data.push_name && (
            <div className="mt-0.5 truncate text-xs text-linen-600">{event.data.push_name}</div>
          )}
          <p className="mt-1 line-clamp-2 text-sm text-ink-soft">
            {event.data.preview ?? '(sin vista previa)'}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                event.data.direction === 'in' ? 'bg-ok' : 'bg-linen-400'
              }`}
            />
            <span className="plate-label">
              {event.data.direction === 'in' ? 'Recibido' : 'Enviado'}
            </span>
          </div>
        </article>
      ))}
    </div>
  )
}
