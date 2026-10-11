import { FeedEvent } from '../types'

export function MessageFeed({ events }: { events: FeedEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        Sin eventos todavía. Envía un mensaje al webhook para verlo aquí.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {events.map((event, index) => (
        <div key={event.id} className="border rounded-lg p-4">
          <div className="flex justify-between items-start mb-2">
            <span className="font-semibold">{event.data.contact_wa_id ?? 'Desconocido'}</span>
            <span className="text-xs text-gray-500">
              {new Date(event.created_at).toLocaleTimeString('es-CO', { hour12: false })}
            </span>
          </div>
          {event.data.push_name && (
            <div className="text-sm font-medium mb-1">
              {event.data.push_name}
            </div>
          )}
          <div className="text-sm text-gray-600">
            {event.data.preview ?? '(sin vista previa)'}
          </div>
          <div className="mt-2 text-xs text-gray-500">
            Tipo: {event.data.direction === 'in' ? 'Entrante' : 'Saliente'}
          </div>
        </div>
      ))}
    </div>
  )
}