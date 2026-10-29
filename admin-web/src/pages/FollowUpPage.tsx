// Seguimiento de cotizaciones: sub-servicio del Cotizador. Su interruptor
// vive aquí (no en la lista de Servicios) porque es parte de este workspace.

import { useState } from 'react'
import { FollowUpPendingItem } from '../types'
import { Card } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { Switch } from "../components/ui/switch"
import { ErrorSlip } from "../components/ui/error-slip"
import { useAuth } from '../auth/AuthContext'
import { useFollowupPending, useRunFollowup } from '../hooks/useFollowup'
import { useModules, useToggleModule } from '../hooks/useModules'
import { formatCOP, formatDate } from '../lib/format'

export default function FollowUpPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { data, isLoading, error } = useFollowupPending()
  const runFollowup = useRunFollowup()
  const { data: modules } = useModules()
  const toggleModule = useToggleModule()
  const [runResult, setRunResult] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)
  const followUpModule = modules?.find((m) => m.key === 'follow_up')

  const handleToggle = (value: boolean) => {
    setToggling(true)
    toggleModule.mutate(
      { moduleKey: 'follow_up', isEnabled: value },
      { onSettled: () => setToggling(false) }
    )
  }

  const handleRun = () => {
    setRunResult(null)
    runFollowup.mutate(undefined, {
      onSuccess: (result) => {
        const parts: string[] = []
        if (result.round1_sent > 0) {
          parts.push(`${result.round1_sent} primer recordatorio${result.round1_sent === 1 ? '' : 's'}`)
        }
        if (result.round2_sent > 0) {
          parts.push(`${result.round2_sent} cierre${result.round2_sent === 1 ? '' : 's'}`)
        }
        if (result.errors > 0) {
          parts.push(`${result.errors} errore${result.errors === 1 ? '' : 's'}`)
        }
        setRunResult(
          parts.length > 0
            ? `Ronda ejecutada: ${parts.join(' · ')}.`
            : 'Ronda ejecutada: no había cotizaciones que necesitaran seguimiento ahora mismo.'
        )
      },
    })
  }

  const items = data?.items ?? []

  return (
    <div>
      {/* Sub-servicio de Cotizador: su interruptor vive aquí */}
      {isAdmin && followUpModule && (
        <Card className="mb-6 flex flex-wrap items-center justify-between gap-3 p-4">
          <div>
            <p className="text-sm font-semibold text-ink">
              Sub-servicio de Cotizador
              <span
                className={`ml-2 rounded-full px-2 py-1 text-xs font-medium ${
                  followUpModule.is_enabled
                    ? 'bg-ok-wash text-ok'
                    : 'bg-linen-100 text-linen-600'
                }`}
              >
                {followUpModule.is_enabled ? 'En servicio' : 'Apagado'}
              </span>
            </p>
            <p className="mt-1 max-w-xl text-xs text-linen-600">
              Encendido: el bot escribe a los 3 y 7 días a los clientes que no
              han respondido su cotización. Apagado: las cotizaciones esperan
              quietas.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              checked={followUpModule.is_enabled}
              disabled={toggling}
              onCheckedChange={handleToggle}
            />
            <span className="text-sm" style={{ color: 'var(--color-ink)' }}>Encender o apagar el seguimiento</span>
          </div>
        </Card>
      )}

      {/* Desk header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink">Cotizaciones enviadas</h2>
          <p className="mt-1 text-sm text-linen-600">
            El asistente escribe a los 3 días y cierra a los 7; quien respondió, no se molesta.
          </p>
        </div>
        {isAdmin && (
          <Button type="button" onClick={handleRun} disabled={runFollowup.isLoading}>
            {runFollowup.isLoading ? 'Ejecutando…' : 'Ejecutar seguimiento ahora'}
          </Button>
        )}
      </div>

      {(runResult || runFollowup.error) && (
        <div className="mb-4 space-y-3">
          {runResult && (
            <div className="ficha px-4 py-3 text-sm text-ink-soft">{runResult}</div>
          )}
          <ErrorSlip message={runFollowup.error?.message ?? null} />
        </div>
      )}

      {error && (
        <div className="mb-4">
          <ErrorSlip message={error.message} />
        </div>
      )}

      {/* Pending table */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-linen-100">
            {[0, 1, 2, 3, 4].map((index: number) => (
              <div key={index} className="flex h-12 items-center gap-4 px-4">
                <div className="skel h-4 w-1/4" />
                <div className="skel h-4 w-20" />
                <div className="skel ml-auto h-4 w-28" />
              </div>
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  <th className="plate-label px-4 py-3 font-semibold">Cliente</th>
                  <th className="plate-label px-4 py-3 font-semibold">Enviada</th>
                  <th className="plate-label px-4 py-3 font-semibold">Total</th>
                  <th className="plate-label px-4 py-3 font-semibold">Seguimiento</th>
                  <th className="plate-label px-4 py-3 font-semibold">Respuesta</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item: FollowUpPendingItem) => (
                  <tr
                    key={item.quote_id}
                    className="border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-ink">{item.contact_name ?? 'Sin nombre'}</div>
                      <div className="tabular text-xs text-linen-600">{item.contact_wa_id}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="tabular text-ink-soft">
                        hace {item.days_elapsed} {item.days_elapsed === 1 ? 'día' : 'días'}
                      </div>
                      <div className="tabular text-xs text-linen-600">
                        {formatDate(item.sent_at)}
                      </div>
                    </td>
                    <td className="tabular px-4 py-3 font-medium text-ink">
                      {formatCOP(item.total)}
                    </td>
                    <td className="px-4 py-3">
                      {item.round2_sent_at ? (
                        <span className="rounded-full bg-brass-wash px-2 py-1 text-xs font-medium text-brass-ink">
                          Cierre enviado
                        </span>
                      ) : item.round1_sent_at ? (
                        <span className="rounded-full bg-pine-wash px-2 py-1 text-xs font-medium text-pine">
                          Recordatorio 1
                        </span>
                      ) : (
                        <span className="rounded-full bg-linen-100 px-2 py-1 text-xs font-medium text-linen-600">
                          En espera
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {item.replied ? (
                        <span className="rounded-full bg-ok-wash px-2 py-1 text-xs font-medium text-ok">
                          Respondió
                        </span>
                      ) : (
                        <span className="text-xs text-linen-600">Sin respuesta</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-medium text-ink">No hay cotizaciones enviadas</p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
              Cuando marques una cotización como «Enviada» aparecerá aquí y el asistente
              empezará a hacerle seguimiento automático a los 3 y 7 días.
            </p>
          </div>
        )}
      </Card>
    </div>
  )
}
