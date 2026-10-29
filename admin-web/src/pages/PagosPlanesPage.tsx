// Pagos y planes — vista dual:
// • Dueño del bot: su plan actual, costo y próxima renovación.
// • Super admin: precios globales, suscripciones de todos los clientes.

import { useEffect, useState } from 'react'
import { Card } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { Input } from "../components/ui/input"
import { ErrorSlip } from "../components/ui/error-slip"
import { useAuth } from '../auth/AuthContext'
import { usePlanPrices, useUpdatePlanPrice } from '../hooks/usePlans'
import { useAdminTenants } from '../hooks/useAdminTenants'
import { formatDate } from '../lib/format'
import { PlanPrice, TenantSummary } from '../types'

const PLAN_BADGES: Record<string, string> = {
  trial: 'bg-linen-100 text-linen-600',
  freemium: 'bg-brass/20 text-brass-deep',
  premium: 'bg-ok-wash text-ok',
}

const PLAN_LABELS: Record<string, string> = {
  trial: 'Prueba gratuita',
  freemium: 'Freemium',
  premium: 'Premium',
}

function formatCOP(value: number): string {
  return `$${value.toLocaleString('es-CO')}`
}

// ── Vista del dueño del bot: su propio plan ──────────────────────────────────
function MyPlanView() {
  const { user } = useAuth()
  const { data: plans, isLoading } = usePlanPrices()

  // Intentamos inferir el plan del tenant desde los datos del usuario
  // (En el futuro el JWT debería incluir el plan directamente)
  const myPlan = (user as any)?.plan ?? 'freemium'
  const myPlanLabel = PLAN_LABELS[myPlan] ?? myPlan
  const planData = plans?.find((p: PlanPrice) => p.plan === myPlan)

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>Mi plan</h1>
        <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          El plan activo de tu cuenta en Aura.
        </p>
      </div>

      <Card className="p-6 mb-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="plate-label mb-1">Plan actual</div>
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ${PLAN_BADGES[myPlan] ?? 'bg-linen-100 text-linen-600'}`}>
                {myPlanLabel}
              </span>
            </div>
            {planData && myPlan !== 'trial' && (
              <p className="mt-3 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
                Precio: <span className="font-semibold" style={{ color: 'var(--color-ink)' }}>{formatCOP(planData.price_cop)} / mes</span>
              </p>
            )}
          </div>
          {myPlan === 'freemium' && (
            <div className="rounded-lg p-4" style={{ background: 'var(--color-brand-magenta-wash)', border: '1px solid var(--color-brand-magenta-border)' }}>
              <p className="text-sm font-semibold" style={{ color: 'var(--color-brand-magenta)' }}>¿Quieres más funciones?</p>
              <p className="text-xs mt-1" style={{ color: 'var(--color-ink-muted)' }}>
                Escríbele al bot para actualizar a Premium y desbloquear todos los servicios.
              </p>
            </div>
          )}
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-sm font-semibold text-ink mb-3">Servicios incluidos en tu plan</h2>
        {isLoading ? (
          <div className="space-y-2">
            <div className="skel h-8 w-full" />
            <div className="skel h-8 w-full" />
          </div>
        ) : (
          <p className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>
            Revisa la sección <strong>Mis servicios</strong> para ver y activar las herramientas disponibles en tu plan.
          </p>
        )}
        <p className="mt-4 text-xs" style={{ color: 'var(--color-ink-muted)' }}>
          ¿Preguntas sobre pagos o facturación? Escríbele directamente al bot.
        </p>
      </Card>
    </div>
  )
}

// ── Fila editable de precio (solo super admin) ────────────────────────────────
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
      <div className="min-w-35 flex-1">
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
          onChange={(e) => setPrice(e.target.value)}
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

  // Los dueños del bot ven su propio plan; el super admin ve la vista global.
  if (!user?.is_platform_admin) {
    return <MyPlanView />
  }

  const premium = tenants?.filter((t) => t.plan === 'premium') ?? []
  const withSub = tenants?.filter((t) => t.subscription_status) ?? []

  return (
    <div className="animate-fade-in">
      <div className="mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap mb-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>Pagos y planes</h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              Precios de los planes, suscripciones activas y el estado de los pagos de los clientes.
            </p>
          </div>
          <span className="rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wider"
            style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}>
            Super Admin
          </span>
        </div>
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
            {(plans ?? []).map((plan: PlanPrice) => (
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
            {(tenants ?? []).map((t: TenantSummary) => (
              <div key={t.id} className="flex flex-wrap items-center gap-3 py-3">
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${
                    PLAN_BADGES[t.plan] ?? 'bg-linen-100 text-linen-600'
                  }`}
                >
                  {t.plan_label}
                </span>
                <span className="min-w-40 flex-1 text-sm font-medium text-ink">
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
