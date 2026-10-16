import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../auth/AuthContext'
import {
  fetchAdminTenants,
  fetchAdminTenant,
  updateAdminTenant,
  changeAdminTenantPlan,
  setAdminTenantWhatsapp,
  fetchAdminConversations,
  fetchAdminMessages,
  addAdminPaymentMethod,
  createTenantCheckoutLink,
} from '../lib/api'
import type {
  TenantSummary,
  TenantDetail,
  TenantCheckoutResult,
  TenantConversation,
  TenantMessage,
} from '../types'

const PLAN_BADGES: Record<string, string> = {
  trial: 'bg-blue-100 text-blue-800',
  freemium: 'bg-amber-100 text-amber-800',
  premium: 'bg-emerald-100 text-emerald-800',
}

export default function AdminPage() {
  const { user } = useAuth()
  const [tenants, setTenants] = useState<TenantSummary[]>([])
  const [selected, setSelected] = useState<TenantDetail | null>(null)
  const [conversations, setConversations] = useState<TenantConversation[]>([])
  const [messages, setMessages] = useState<TenantMessage[]>([])
  const [activeConv, setActiveConv] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [checkoutLink, setCheckoutLink] = useState<TenantCheckoutResult | null>(null)

  const loadTenants = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAdminTenants()
      setTenants(data)
    } catch (e: any) {
      setError(e.message || 'Error cargando clientes')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (id: string) => {
    try {
      const [detail, convs] = await Promise.all([
        fetchAdminTenant(id),
        fetchAdminConversations(id),
      ])
      setSelected(detail)
      setConversations(convs.items)
      setMessages([])
      setActiveConv(null)
    } catch (e: any) {
      setError(e.message || 'Error cargando detalle')
    }
  }, [])

  const loadMessages = useCallback(
    async (tenantId: string, conversationId: string) => {
      try {
        const data = await fetchAdminMessages(tenantId, conversationId)
        setMessages(data.items)
        setActiveConv(conversationId)
      } catch (e: any) {
        setError(e.message || 'Error cargando mensajes')
      }
    },
    []
  )

  useEffect(() => {
    if (user?.is_platform_admin) {
      loadTenants()
    }
  }, [user, loadTenants])

  const handleSave = async (field: string, value: string | boolean) => {
    if (!selected) return
    setSaving(true)
    try {
      const updated = await updateAdminTenant(selected.id, { [field]: value })
      setSelected(updated)
    } catch (e: any) {
      setError(e.message || 'Error guardando')
    } finally {
      setSaving(false)
    }
  }

  const handlePlanChange = async (plan: string) => {
    if (!selected) return
    setSaving(true)
    try {
      const updated = await changeAdminTenantPlan(selected.id, plan)
      setSelected(updated)
      loadTenants()
    } catch (e: any) {
      setError(e.message || 'Error cambiando plan')
    } finally {
      setSaving(false)
    }
  }

  const handleWhatsapp = async (waId: string) => {
    if (!selected) return
    setSaving(true)
    try {
      const updated = await setAdminTenantWhatsapp(selected.id, waId || null)
      setSelected(updated)
    } catch (e: any) {
      setError(e.message || 'Error guardando WhatsApp')
    } finally {
      setSaving(false)
    }
  }

  const handleCheckout = async () => {
    if (!selected) return
    setSaving(true)
    try {
      const result = await createTenantCheckoutLink(selected.id)
      setCheckoutLink(result)
    } catch (e: any) {
      setError(e.message || 'Error creando link de pago')
    } finally {
      setSaving(false)
    }
  }

  const handleAddPaymentMethod = async () => {
    if (!selected) return
    const brand = prompt('Marca de la tarjeta (ej: Visa, Mastercard):')
    if (!brand) return
    const last4 = prompt('Últimos 4 dígitos:')
    if (!last4 || !/^\d{4}$/.test(last4)) {
      alert('Los últimos 4 dígitos deben ser numéricos')
      return
    }
    setSaving(true)
    try {
      const updated = await addAdminPaymentMethod(selected.id, { brand, last4 })
      setSelected(updated)
    } catch (e: any) {
      setError(e.message || 'Error agregando método de pago')
    } finally {
      setSaving(false)
    }
  }

  if (!user?.is_platform_admin) {
    return (
      <div className="p-8 text-center">
        <p className="text-lg font-semibold text-stone-700">
          Esta sección es solo para el administrador de la plataforma.
        </p>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-900">
          Administración de la Plataforma
        </h1>
        <p className="mt-1 text-sm text-stone-500">
          Gestiona tus clientes, planes, servicios y conversaciones.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-stone-500">Cargando…</p>}

      {/* Tabla de clientes */}
      <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-200 bg-stone-50 text-left text-xs uppercase tracking-wider text-stone-500">
              <th className="px-4 py-3">Negocio</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">WhatsApp</th>
              <th className="px-4 py-3">Servicios</th>
              <th className="px-4 py-3">Contactos</th>
              <th className="px-4 py-3">Cotizaciones</th>
              <th className="px-4 py-3">Mensajes</th>
              <th className="px-4 py-3">Tipo</th>
            </tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr
                key={t.id}
                onClick={() => loadDetail(t.id)}
                className={`cursor-pointer border-b border-stone-100 transition-colors hover:bg-stone-50 ${
                  selected?.id === t.id ? 'bg-stone-100' : ''
                }`}
              >
                <td className="px-4 py-3">
                  <div className="font-medium text-stone-900">{t.name}</div>
                  <div className="text-xs text-stone-400">{t.slug}</div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      PLAN_BADGES[t.plan] || 'bg-stone-100 text-stone-600'
                    }`}
                  >
                    {t.plan_label}
                  </span>
                </td>
                <td className="px-4 py-3 text-stone-600">
                  {t.wa_id || <span className="text-stone-300">—</span>}
                </td>
                <td className="px-4 py-3 text-stone-600">
                  {t.enabled_modules}/{t.total_modules}
                </td>
                <td className="px-4 py-3 text-stone-600">{t.contacts}</td>
                <td className="px-4 py-3 text-stone-600">{t.quotes}</td>
                <td className="px-4 py-3 text-stone-600">{t.messages}</td>
                <td className="px-4 py-3 text-stone-600">
                  {t.account_type === 'business' ? '🏢' : '👤'}
                  {t.nit ? ` ${t.nit}` : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detalle del cliente seleccionado */}
      {selected && (
        <div className="mt-6 rounded-lg border border-stone-200 bg-white p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-lg font-bold text-stone-900">
                {selected.name}
              </h2>
              <p className="text-sm text-stone-500">
                Bot: {selected.bot_name} ·{' '}
                {selected.account_type === 'business'
                  ? `Empresa · NIT ${selected.nit || '—'}`
                  : 'Persona natural'}
              </p>
            </div>
            <button
              onClick={() => setSelected(null)}
              className="text-sm text-stone-400 hover:text-stone-600"
            >
              Cerrar ✕
            </button>
          </div>

          {/* Plan y estado */}
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <label className="text-xs font-semibold uppercase text-stone-400">
                Plan
              </label>
              <select
                value={selected.plan}
                onChange={(e) => handlePlanChange(e.target.value)}
                disabled={saving}
                className="mt-1 w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
              >
                <option value="trial">Prueba</option>
                <option value="freemium">Freemium</option>
                <option value="premium">Premium ($29.000)</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold uppercase text-stone-400">
                WhatsApp del dueño
              </label>
              <input
                type="text"
                defaultValue={selected.wa_id || ''}
                onBlur={(e) => handleWhatsapp(e.target.value.trim())}
                disabled={saving}
                placeholder="573001234567"
                className="mt-1 w-full rounded-md border border-stone-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase text-stone-400">
                Atención al cliente
              </label>
              <button
                onClick={() => handleSave('customer_mode', !selected.customer_mode)}
                disabled={saving}
                className={`mt-1 w-full rounded-md px-3 py-2 text-sm font-medium ${
                  selected.customer_mode
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-stone-100 text-stone-600'
                }`}
              >
                {selected.customer_mode ? '✅ Activada' : '⛔ Desactivada'}
              </button>
            </div>
          </div>

          {/* Suscripción y pagos */}
          <div className="mt-6">
            <h3 className="text-sm font-bold uppercase tracking-wide text-stone-500">
              Suscripción y Pagos
            </h3>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {selected.subscription && (
                <span className="text-sm text-stone-600">
                  Estado:{' '}
                  <strong>{selected.subscription.status}</strong>
                  {selected.subscription.current_period_end &&
                    ` · Vence: ${new Date(selected.subscription.current_period_end).toLocaleDateString('es-CO')}`}
                </span>
              )}
              <button
                onClick={handleAddPaymentMethod}
                disabled={saving}
                className="rounded-md bg-stone-200 px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-300"
              >
                + Registrar tarjeta
              </button>
              <button
                onClick={handleCheckout}
                disabled={saving}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
              >
                🔗 Link de pago (MercadoPago)
              </button>
            </div>
            {checkoutLink?.init_point && (
              <a
                href={checkoutLink.init_point}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 block text-sm text-emerald-600 underline"
              >
                {checkoutLink.init_point}
              </a>
            )}
            {selected.payment_methods.length > 0 && (
              <ul className="mt-3 space-y-1">
                {selected.payment_methods.map((pm) => (
                  <li key={pm.id} className="text-sm text-stone-600">
                    💳 {pm.brand} •••• {pm.last4}
                    {pm.is_default && ' (predeterminada)'}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Servicios */}
          <div className="mt-6">
            <h3 className="text-sm font-bold uppercase tracking-wide text-stone-500">
              Servicios ({selected.enabled_modules}/{selected.total_modules})
            </h3>
            <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
              {selected.modules.map((m) => (
                <div
                  key={m.key}
                  className={`rounded-md border p-2 text-xs ${
                    m.is_enabled
                      ? 'border-emerald-300 bg-emerald-50'
                      : m.entitled
                        ? 'border-stone-200 bg-white'
                        : 'border-stone-100 bg-stone-50 opacity-50'
                  }`}
                >
                  <div className="font-medium text-stone-800">{m.name}</div>
                  <div className="text-stone-400">
                    {m.dev_status === 'active' ? '✅' : '🔨 En desarrollo'}
                    {!m.entitled && ' · Fuera de plan'}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Historial de chat */}
          <div className="mt-6">
            <h3 className="text-sm font-bold uppercase tracking-wide text-stone-500">
              Historial de Chat
            </h3>
            <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2">
              {/* Lista de conversaciones */}
              <div className="max-h-64 overflow-y-auto rounded-md border border-stone-200">
                {conversations.length === 0 ? (
                  <p className="p-4 text-center text-sm text-stone-400">
                    Sin conversaciones
                  </p>
                ) : (
                  conversations.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => loadMessages(selected.id, c.id)}
                      className={`w-full border-b border-stone-100 px-3 py-2 text-left text-sm hover:bg-stone-50 ${
                        activeConv === c.id ? 'bg-stone-100' : ''
                      }`}
                    >
                      <div className="font-medium text-stone-800">
                        {c.contact_name || c.contact_wa_id}
                      </div>
                      <div className="text-xs text-stone-400">
                        {c.messages_count} mensajes
                        {c.last_message_at &&
                          ` · ${new Date(c.last_message_at).toLocaleDateString('es-CO')}`}
                      </div>
                    </button>
                  ))
                )}
              </div>
              {/* Mensajes de la conversación */}
              <div className="max-h-64 overflow-y-auto rounded-md border border-stone-200 bg-stone-50 p-3">
                {messages.length === 0 ? (
                  <p className="text-center text-sm text-stone-400">
                    Selecciona una conversación
                  </p>
                ) : (
                  messages.map((m) => (
                    <div
                      key={m.id}
                      className={`mb-2 max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                        m.direction === 'in'
                          ? 'ml-0 bg-white text-stone-800'
                          : 'ml-auto bg-emerald-100 text-stone-800'
                      }`}
                    >
                      {m.content || `[${m.type}]`}
                      <div className="mt-0.5 text-[0.65rem] text-stone-400">
                        {new Date(m.created_at).toLocaleString('es-CO')}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
