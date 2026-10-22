// MessageFeed v2 — Dark Premium.
// Fichas de mensajes en tiempo real con animación de entrada.

import { FeedEvent } from '../types'

export function MessageFeed({ events }: { events: FeedEvent[] }) {
  if (events.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-xl px-6 py-12 text-center"
        style={{
          background: 'var(--color-bg-card)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        <div
          className="mb-3 flex h-12 w-12 items-center justify-center rounded-full"
          style={{ background: 'var(--color-bg-raised)' }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-6 w-6" style={{ color: 'var(--color-text-tertiary)' }}>
            <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
          </svg>
        </div>
        <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Sin mensajes todavía
        </p>
        <p className="mt-1 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          Cuando un cliente escriba al WhatsApp conectado, su actividad aparecerá aquí en tiempo real.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {events.map((event, i) => (
        <article
          key={event.id}
          className="animate-fade-in rounded-xl px-4 py-3"
          style={{
            animationDelay: `${i * 30}ms`,
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
          }}
        >
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="flex items-center gap-2 min-w-0">
              {/* Avatar iniciales */}
              <div
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                style={{
                  background: event.data.direction === 'in'
                    ? 'rgba(59,130,246,0.15)'
                    : 'rgba(124,58,237,0.15)',
                  color: event.data.direction === 'in' ? '#60a5fa' : '#a78bfa',
                }}
              >
                {(event.data.push_name ?? event.data.contact_wa_id ?? '?')[0].toUpperCase()}
              </div>
              <span className="truncate text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                {event.data.push_name ?? event.data.contact_wa_id ?? 'Desconocido'}
              </span>
              <span
                className="shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                style={{
                  background: event.data.direction === 'in'
                    ? 'rgba(59,130,246,0.1)'
                    : 'rgba(124,58,237,0.1)',
                  color: event.data.direction === 'in' ? '#60a5fa' : '#a78bfa',
                }}
              >
                {event.data.direction === 'in' ? '← recibido' : '→ enviado'}
              </span>
            </div>
            <time
              className="tabular shrink-0 text-xs"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              {new Date(event.created_at).toLocaleTimeString('es-CO', { hour12: false })}
            </time>
          </div>
          {event.data.preview && (
            <p className="ml-8 line-clamp-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {event.data.preview}
            </p>
          )}
        </article>
      ))}
    </div>
  )
}
