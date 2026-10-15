// Clientes de la plataforma (superadmin): los negocios que tienen el
// asistente — su plan, su uso y su suscripción. Adendo §3.3.
// (Los clientes de CADA negocio viven en el CRM del dueño: /servicios/crm.)

import { useEffect, useState } from 'react'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Modal from '../components/ui/modal'
import ErrorSlip from '../components/ui/error-slip'
import { useAuth } from '../auth/AuthContext'
import {
  useAdminTenant,
  useAdminTenants,
  useChangeTenantPlan,
  useTenantCheckoutLink,
} from '../hooks/useAdminTenants'
import { formatDate } from '../lib/format'
import { TenantSummary } from '../types'

const PLAN_BADGES: Record<string, string> = {
  trial: 'bg-linen-100 text-linen-600',
  freemium: 'bg-brass/20 text-brass-deep',
  premium: 'bg-ok-wash text-ok',
}

function TenantFicha({
  tenantId,
  onClose,
}: {
  tenantId: string
  onClose: () => void
}) {
  const { data: tenant, isLoading, error } = useAdminTenant(tenantId)
  const changePlan = useChangeTenantPlan()
  const checkout = useTenantCheckoutLink()
  const [newPlan, setNewPlan] = useState('')
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (tenant) {
      setNewPlan(tenant.plan)
      setFormError(null)
    }
  }, [tenant])

  const handlePlan = () => {
    if (!tenant || newPlan === tenant.plan) return
    if (
      !window.confirm(
        `¿Cambiar el plan de ${tenant.name} a ${newPlan}? Los servicios se ajustan al nuevo plan.`
      )
    ) {
      return
    }
    changePlan.mutate(
      { id: tenant.id, plan: newPlan },
      { onError: (err) => setFormError(err.message) }
    )
  }

  const handleCheckout = () => {
    if (!tenant) return
    setFormError(null)
    checkout.mutate(tenant.id, {
      onSuccess: (result) => setCheckoutUrl(result.init_point),
      onError: (err) => setFormError(err.message),
    })
  }

  return (
    <Modal open onClose={onClose} title="Ficha del negocio" wide>
      {isLoading && (
        <div className="space-y-3">
          <div className="skel h-5 w-1/2" />
          <div className="skel h-4 w-1/3" />
          <div className="skel h-24 w-full" />
        </div>
      )}
      {error && <ErrorSlip message={error.message} />}
      {tenant && (
        <div className="space-y-5">
          {/* Identidad */}
          <div className="flex flex-wrap items-center gap-3">
            <div>
              <div className="text-base font-semibold text-ink">{tenant.name}</div>
              <div className="tabular text-xs text-linen-600">
                {tenant.slug} · bot: {tenant.bot_name}
                {tenant.wa_id ? ` · WhatsApp ${tenant.wa_id}` : ''}
              </div>
            </div>
            <span
              className={`ml-auto rounded-full px-2.5 py-1 text-xs font-medium ${
                PLAN_BADGES[tenant.plan] ?? 'bg-linen-100 text-linen-600'
              }`}
            >
              {tenant.plan_label}
              {tenant.plan_price_cop > 0
                ? ` · $${tenant.plan_price_cop.toLocaleString('es-CO')}/mes`
                : ''}
            </span>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                tenant.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
              }`}
            >
              {tenant.is_active ? 'Activo' : 'Inactivo'}
            </span>
          </div>

          {/* Uso del asistente */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Contactos</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {tenant.contacts}
              </div>
            </div>
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Cotizaciones</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {tenant.quotes}
              </div>
            </div>
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Mensajes</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {tenant.messages}
              </div>
            </div>
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Usuarios</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {tenant.users}
              </div>
            </div>
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Servicios</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {tenant.enabled_modules}/{tenant.total_modules}
              </div>
            </div>
          </div>

          {/* Suscripción */}
          {tenant.subscription && (
            <p className="text-xs text-linen-600">
              Suscripción <b>{tenant.subscription.status}</b> vía{' '}
              {tenant.subscription.provider}
              {tenant.subscription.current_period_end
                ? ` · renueva el ${formatDate(tenant.subscription.current_period_end)}`
                : ''}
            </p>
          )}

          {/* Servicios del negocio */}
          <div>
            <h3 className="plate-label mb-2">Servicios de este negocio</h3>
            <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
              {tenant.modules.map((module) => (
                <div
                  key={module.key}
                  className="ficha flex items-center gap-2 px-3 py-1.5"
                >
                  <span className="min-w-[150px] flex-1 truncate text-sm text-ink-soft">
                    {module.name}
                  </span>
                  {module.dev_status === 'development' && (
                    <span className="text-xs text-linen-600">En desarrollo</span>
                  )}
                  {module.dev_status === 'active' && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        module.is_enabled
                          ? 'bg-ok-wash text-ok'
                          : 'bg-linen-100 text-linen-600'
                      }`}
                    >
                      {module.is_enabled ? 'Encendido' : 'Apagado'}
                    </span>
                  )}
                  {!module.entitled && (
                    <span className="text-xs text-lacre" title="No incluido en su plan">
                      fuera del plan
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Métodos de pago */}
          {tenant.payment_methods.length > 0 && (
            <div>
              <h3 className="plate-label mb-2">Métodos de pago</h3>
              {tenant.payment_methods.map((pm) => (
                <p key={pm.id} className="text-sm text-ink-soft">
                  {pm.brand} •••• {pm.last4}
                  {pm.is_default ? ' · principal' : ''}
                </p>
              ))}
            </div>
          )}

          {/* Acciones */}
          <div className="flex flex-wrap items-end gap-3 border-t border-linen-100 pt-4">
            <div className="w-44">
              <label className="mb-1 block text-xs font-medium text-ink-soft" htmlFor="tenant-plan">
                Cambiar plan
              </label>
              <select
                id="tenant-plan"
                value={newPlan}
                onChange={(e) => setNewPlan(e.target.value)}
                className="h-11 w-full rounded-md border border-linen-300 bg-panel px-2 text-sm text-ink"
                aria-label="Plan del negocio"
              >
                <option value="trial">Prueba</option>
                <option value="freemium">Freemium</option>
                <option value="premium">Premium</option>
              </select>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={handlePlan}
              disabled={changePlan.isLoading || newPlan === tenant.plan}
            >
              {changePlan.isLoading ? 'Aplicando…' : 'Aplicar plan'}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCheckout}
              disabled={checkout.isLoading}
            >
              {checkout.isLoading ? 'Generando…' : 'Generar link de pago'}
            </Button>
            {checkoutUrl && (
              <p className="w-full break-all text-xs text-ok">
                Link de pago listo:{' '}
                <a href={checkoutUrl} target="_blank" rel="noreferrer" className="underline">
                  {checkoutUrl}
                </a>
              </p>
            )}
            {formError && <ErrorSlip message={formError} />}
          </div>
        </div>
      )}
    </Modal>
  )
}

function ClientsSection() {
  const { data, isLoading, error } = useAdminTenants()
  const [openId, setOpenId] = useState<string | null>(null)

  return (
    <Card className="p-5">
      <div className="mb-1 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">Mis clientes</h2>
        <span className="tabular text-xs text-linen-600">
          {data?.length ?? 0} negocios con el asistente
        </span>
      </div>
      <p className="mb-4 text-xs text-linen-600">
        Los negocios suscritos: su plan, su uso del asistente y su suscripción.
        (Los clientes de CADA negocio se gestionan en su propio módulo de Contactos.)
      </p>
      {error && (
        <div className="mb-3">
          <ErrorSlip message={error.message} />
        </div>
      )}
      {isLoading ? (
        <div className="space-y-2">
          <div className="skel h-14 w-full" />
          <div className="skel h-14 w-full" />
        </div>
      ) : (data?.length ?? 0) === 0 ? (
        <p className="py-4 text-center text-sm text-linen-600">
          Todavía no hay negocios con el asistente.
        </p>
      ) : (
        <div className="divide-y divide-linen-100">
          {data?.map((tenant: TenantSummary) => (
            <div key={tenant.id} className="flex flex-wrap items-center gap-3 py-3">
              <span
                className={`rounded-full px-2 py-1 text-xs font-medium ${
                  PLAN_BADGES[tenant.plan] ?? 'bg-linen-100 text-linen-600'
                }`}
              >
                {tenant.plan_label}
              </span>
              <div className="min-w-[160px] flex-1">
                <div className="text-sm font-medium text-ink">{tenant.name}</div>
                <div className="tabular text-xs text-linen-600">
                  {tenant.contacts} contactos · {tenant.quotes} cotizaciones ·{' '}
                  {tenant.messages} mensajes · {tenant.enabled_modules} servicios
                </div>
              </div>
              <span
                className={`rounded-full px-2 py-1 text-xs font-medium ${
                  tenant.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
                }`}
              >
                {tenant.is_active ? 'Activo' : 'Inactivo'}
              </span>
              <Button type="button" variant="outline" size="sm" onClick={() => setOpenId(tenant.id)}>
                Abrir ficha
              </Button>
            </div>
          ))}
        </div>
      )}
      {openId && <TenantFicha tenantId={openId} onClose={() => setOpenId(null)} />}
    </Card>
  )
}

export default function PlatformClientesPage() {
  const { user } = useAuth()

  if (!user?.is_platform_admin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">
          Solo el administrador de la plataforma ve sus clientes.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Clientes</h1>
        <p className="mt-1 text-sm text-linen-600">
          Los negocios que tienen el asistente: su plan, su uso y su suscripción.
        </p>
      </div>

      <ClientsSection />
    </div>
  )
}
