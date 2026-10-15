// Agenda: recordatorios programados — por chat o desde aquí.
// El bot escribe al dueño por WhatsApp cuando llega la hora.

import { useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Input from '../components/ui/input'
import ErrorSlip from '../components/ui/error-slip'
import { IconArrowLeft } from '../components/ui/icons'
import {
  useCreateReminder,
  useReminders,
  useSetReminderStatus,
} from '../hooks/useReminders'

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  sent: { label: 'Enviado', className: 'bg-ok-wash text-ok' },
  done: { label: 'Hecho', className: 'bg-ok-wash text-ok' },
  cancelled: { label: 'Cancelado', className: 'bg-linen-100 text-linen-600' },
}

export default function RemindersPage() {
  const pending = useReminders('pending')
  const history = useReminders()
  const create = useCreateReminder()
  const setStatus = useSetReminderStatus()
  const [content, setContent] = useState('')
  const [when, setWhen] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const now = new Date()

  const handleCreate = () => {
    if (!content.trim() || !when) return
    setFormError(null)
    create.mutate(
      { content: content.trim(), remindAt: new Date(when).toISOString() },
      {
        onSuccess: () => {
          setContent('')
          setWhen('')
        },
        onError: (err) => setFormError(err.message),
      }
    )
  }

  const handleClose = (id: string, status: 'done' | 'cancelled') => {
    if (status === 'cancelled' && !window.confirm('¿Cancelar este recordatorio?')) {
      return
    }
    setStatus.mutate({ id, status }, { onError: (err) => setFormError(err.message) })
  }

  const historyItems = (history.data ?? []).filter((r) => r.status !== 'pending')

  return (
    <div>
      <Link
        to="/servicios"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-pine hover:underline"
      >
        <IconArrowLeft className="h-4 w-4" />
        Servicios
      </Link>

      <div className="mt-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Agenda</h1>
        <p className="mt-1 text-sm text-linen-600">
          Recordatorios que el bot enviará por WhatsApp a su hora. También los
          puedes crear por chat: «recuérdame llamar al cliente el jueves».
        </p>
      </div>

      <div className="mb-4">
        <ErrorSlip
          message={formError ?? pending.error?.message ?? history.error?.message ?? null}
        />
      </div>

      {/* Programar */}
      <Card className="mb-6 p-5">
        <h2 className="mb-1 text-sm font-semibold text-ink">Programar recordatorio</h2>
        <p className="mb-3 text-xs text-linen-600">
          El bot escribirá al dueño del negocio en la fecha programada.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs font-medium text-ink-soft" htmlFor="remind-content">
              Qué recordar
            </label>
            <Input
              id="remind-content"
              value={content}
              onChangeValue={setContent}
              placeholder="Llamar al cliente de Laureles"
              aria-label="Qué recordar"
            />
          </div>
          <div className="w-56">
            <label className="mb-1 block text-xs font-medium text-ink-soft" htmlFor="remind-when">
              Cuándo
            </label>
            <Input
              id="remind-when"
              type="datetime-local"
              value={when}
              onChangeValue={setWhen}
              aria-label="Fecha y hora del recordatorio"
            />
          </div>
          <Button
            type="button"
            onClick={handleCreate}
            disabled={create.isLoading || !content.trim() || !when}
          >
            {create.isLoading ? 'Programando…' : 'Programar'}
          </Button>
        </div>
      </Card>

      {/* Próximos y vencidos */}
      <Card className="mb-6 p-5">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Próximos y vencidos</h2>
          <span className="tabular text-xs text-linen-600">
            {pending.data?.length ?? 0} pendientes
          </span>
        </div>
        {pending.isLoading ? (
          <div className="space-y-2">
            <div className="skel h-14 w-full" />
            <div className="skel h-14 w-full" />
          </div>
        ) : (pending.data?.length ?? 0) === 0 ? (
          <p className="py-4 text-center text-sm text-linen-600">
            No hay recordatorios pendientes — agenda uno arriba o por chat.
          </p>
        ) : (
          <div className="divide-y divide-linen-100">
            {pending.data?.map((reminder) => {
              const overdue = new Date(reminder.remind_at) < now
              return (
                <div key={reminder.id} className="flex flex-wrap items-center gap-3 py-3">
                  <span
                    className={`rounded-full px-2 py-1 text-xs font-medium ${
                      overdue ? 'bg-lacre-wash text-lacre' : 'bg-brass/20 text-brass-deep'
                    }`}
                  >
                    {overdue ? 'Vencido' : 'Pendiente'}
                  </span>
                  <p className="min-w-[160px] flex-1 text-sm font-medium text-ink">
                    {reminder.content}
                  </p>
                  <time className="tabular text-xs text-linen-600">
                    {formatWhen(reminder.remind_at)}
                  </time>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => handleClose(reminder.id, 'done')}
                      disabled={setStatus.isLoading}
                    >
                      Hecho
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => handleClose(reminder.id, 'cancelled')}
                      disabled={setStatus.isLoading}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {/* Historial */}
      <Card className="p-5">
        <h2 className="mb-2 text-sm font-semibold text-ink">Historial</h2>
        {historyItems.length === 0 ? (
          <p className="py-4 text-center text-sm text-linen-600">
            Aquí aparecerán los recordatorios enviados y cerrados.
          </p>
        ) : (
          <div className="divide-y divide-linen-100">
            {historyItems.slice(0, 20).map((reminder) => {
              const badge = STATUS_BADGES[reminder.status] ?? {
                label: reminder.status,
                className: 'bg-linen-100 text-linen-600',
              }
              return (
                <div key={reminder.id} className="flex flex-wrap items-center gap-3 py-3">
                  <span className={`rounded-full px-2 py-1 text-xs font-medium ${badge.className}`}>
                    {badge.label}
                  </span>
                  <p className="min-w-[160px] flex-1 text-sm text-ink-soft">
                    {reminder.content}
                  </p>
                  <time className="tabular text-xs text-linen-600">
                    {formatWhen(reminder.remind_at)}
                  </time>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}
