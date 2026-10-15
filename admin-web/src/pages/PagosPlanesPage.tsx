// Pagos y planes (superadmin, adendo §3.1): precios de los planes, estado
// de las suscripciones de los clientes y lo que llegará: pagos, webhooks y
// conciliación de MercadoPago.

import { useEffect, useState } from 'react'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Input from '../components/ui/input'
import ErrorSlip from '../components/ui/error-slip'
import { useAuth } from '../auth/AuthContext'
import { usePlanPrices, useUpdatePlanPrice } from '../hooks/usePlans'
import { useAdminTenants } from '../hooks/useAdminTenants'
import { formatDate } from '../lib/format'
import { PlanPrice } from '../types'

const PLAN_BADGES: Record<string, string> = {
  trial: 'bg-linen-100 text-linen-600',
  freemium: 'bg-brass/20 text-brass-deep',
  premium: 'bg-ok-wash text-ok',
}

function formatCOP(value: number): string {
  return `$${value.toLocaleString('es-CO')}`
}

function PlanRow({ plan }: { plan: PlanPrice }) {
  const update = useUpdatePlanPrice()
  const [price, setPrice] = useState(String(plan.price_cop))
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    setPrice(String(plan.price_cop))
  }, [plan.price_cop])

  const parsed = Number(price)
  const dirty = Number.isInteger(parsed) && parsed !== plan.price_cop

  const handleSave = () => {
    if (!Number.isInteger(parsed) || parsed < 0) {
      setNote('El precio debe ser un entero mayor o igual a 0')
      return
    }
    setNote(null)
    update.mutate(
      { plan: plan.plan, priceCop: parsed },
      {
        onSuccess: () => setNote('Precio actualizado ✓'),
        onError: (err) => setNote(`Error: ${err.message}`),
      }
    )
  }

  return (
    <div className="ficha flex flex-wrap items-end gap-3 px-4 py-3">
      <div className="min-w-[140px] flex-1">
        <div className="text-sm font-semibold text-ink">{plan.label}</div>
        <div className="plate-label">{plan.plan}</div>
      </div>
      {plan.is_overridden && (
        <span className="mb-1.5 rounded-full bg-pine-wash px-2 py-1 text-xs font-medium text-pine">
          Personalizado
        </span>
      )}
      <div className="w-40">
        <label className="plate-label mb-1 block" htmlFor={`price-${plan.plan}`}>
          Precio (COP)
        </label>
        <Input
          id={`price-${plan.plan}`}
          value={price}
          onChangeValue={setPrice}
          inputMode="numeric"
          aria-label={`Precio del plan ${plan.label} en pesos colombianos`}
        />
      </div>
      <div className="mb-3 text-sm tabular text-linen-600">
        hoy: <span className="font-medium text-ink-soft">{formatCOP(plan.price_cop)}</span>
      </div>
      <Button
        type="button"
        size="sm"
        onClick={handleSave}
        disabled={!dirty || update.isLoading}
      >
        {update.isLoading ? 'Guardando…' : 'Guardar'}
      </Button>
      {note && (
        <p
          className={`w-full text-xs ${
            note.startsWith('Error') || note.startsWith('El precio')
              ? 'text-lacre'
              : 'text-ok'
          }`}
        >
          {note}
        </p>
      )}
    </div>
  )
}

export default function PagosPlanesPage() {
  const { user } = useAuth()
  const { data: plans, isLoading, error } = usePlanPrices()
  const { data: tenants } = useAdminTenants()

  if (!user?.is_platform_admin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">
          Solo el administrador de la plataforma gestiona pagos y planes.
        </p>
      </div>
    )
  }

  const premium = tenants?.filter((t) => t.plan === 'premium') ?? []
  const withSub = tenants?.filter((t) => t.subscription_status) ?? []

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Pagos y planes</h1>
        <p className="mt-1 text-sm text-linen-600">
          Precios de los planes, suscripciones activas y el estado de los pagos
          de tus clientes.
        </p>
      </div>

      {error && (
        <div className="mb-4">
          <ErrorSlip message={error.message} />
        </div>
      )}

      {/* Precios */}
      <Card className="mb-6 p-5">
        <h2 className="mb-1 text-sm font-semibold text-ink">Precios de los planes</h2>
        <p className="mb-4 text-xs text-linen-600">
          El precio vigente se usa al generar el link de pago y al validar que
          el pago recibido corresponde al plan.
        </p>
        {isLoading ? (
          <div className="space-y-2">
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
          </div>
        ) : (
          <div className="space-y-2">
            {(plans ?? []).map((plan) => (
              <PlanRow key={plan.plan} plan={plan} />
            ))}
          </div>
        )}
      </Card>

      {/* Suscripciones */}
      <Card className="p-5">
        <div className="mb-1 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Suscripciones</h2>
          <span className="tabular text-xs text-linen-600">
            {premium.length} premium · {withSub.length} con suscripción registrada
          </span>
        </div>
        {(tenants?.length ?? 0) === 0 ? (
          <p className="py-4 text-center text-sm text-linen-600">
            Todavía no hay negocios con el asistente.
          </p>
        ) : (
          <div className="divide-y divide-linen-100">
            {(tenants ?? []).map((t) => (
              <div key={t.id} className="flex flex-wrap items-center gap-3 py-3">
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${
                    PLAN_BADGES[t.plan] ?? 'bg-linen-100 text-linen-600'
                  }`}
                >
                  {t.plan_label}
                </span>
                <span className="min-w-[160px] flex-1 text-sm font-medium text-ink">
                  {t.name}
                </span>
                <span className="text-xs text-linen-600">
                  {t.subscription_status
                    ? `Suscripción ${t.subscription_status}`
                    : 'Sin suscripción'}
                </span>
                {t.subscription_period_end && (
                  <time className="tabular text-xs text-linen-600">
                    hasta {formatDate(t.subscription_period_end)}
                  </time>
                )}
              </div>
            ))}
          </div>
        )}
        <p className="mt-4 text-xs text-linen-600">
          Próximamente aquí: pagos recibidos, reembolsos, webhooks de
          MercadoPago y conciliación.
        </p>
      </Card>
    </div>
  )
}
