// Dueños del bot (superadmin): negocios que usan el asistente, su plan, uso
// y suscripción. Los contactos de cada negocio viven en el Mini CRM del dueño.

import { useEffect, useState } from 'react'
import { Card } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { Modal } from "../components/ui/modal"
import { ErrorSlip } from "../components/ui/error-slip"
import { Input } from "../components/ui/input"
import { useAuth } from '../auth/AuthContext'
import {
  useAdminTenant,
  useAdminTenants,
  useChangeTenantPlan,
  useTenantCheckoutLink,
  useSendAdminMessage,
  useAdminConversations,
  useAdminMessages,
  useUpdateTenant,
  useAdminTenantContacts,
  useAdminTenantContact,
  useAdminTenantContactMessages,
  usePlatformAdminStats,
  useUpdateAdminTenantStatus,
} from '../hooks/useAdminTenants'
import { formatDate } from '../lib/format'
import { TenantSummary, TenantPaymentMethod, AdminConversation, AdminMessage, TenantModuleView } from '../types'

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
  const sendAdminMsg = useSendAdminMessage()
  const updateTenant = useUpdateTenant()
  const [newPlan, setNewPlan] = useState('')
  const [checkoutUrl, setCheckoutUrl] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [notifyMsg, setNotifyMsg] = useState('')
  const [notifySent, setNotifySent] = useState(false)

  // Tabs
  const [activeTab, setActiveTab] = useState<'info' | 'contacts' | 'conversations'>('info')

  // Conversaciones
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState('')
  const [activeConvId, setActiveConvId] = useState<string | null>(null)

  // Contactos del dueño
  const [contactSearch, setContactSearch] = useState('')
  const [contactPage, setContactPage] = useState(0)
  const [activeContactId, setActiveContactId] = useState<string | null>(null)
  const { data: convData, isLoading: convLoading, refetch: refetchConvs } = useAdminConversations(tenantId, reason || null)
  const { data: msgData, isLoading: msgLoading } = useAdminMessages(tenantId, activeConvId)

  // Contactos del dueño (cross-tenant)
  const { data: contactsData, isLoading: contactsLoading, refetch: refetchContacts } = useAdminTenantContacts(
    tenantId,
    contactPage * 20,
    20,
    contactSearch || undefined
  )
  const { data: contactDetail, isLoading: contactDetailLoading } = useAdminTenantContact(tenantId, activeContactId)
  const { data: contactMsgData, isLoading: contactMsgLoading } = useAdminTenantContactMessages(tenantId, activeContactId)

  // Edición
  const [editName, setEditName] = useState('')
  const [editBotName, setEditBotName] = useState('')
  const [isEditing, setIsEditing] = useState(false)

  useEffect(() => {
    if (tenant) {
      setNewPlan(tenant.plan)
      setFormError(null)
      setEditName(tenant.name)
      setEditBotName(tenant.bot_name)
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

  const handleNotify = async () => {
    if (!tenant || !notifyMsg.trim() || sendAdminMsg.isLoading) return
    setFormError(null)
    sendAdminMsg.mutate(
      { tenantId: tenant.id, message: notifyMsg.trim() },
      {
        onSuccess: () => {
          setNotifySent(true)
          setNotifyMsg('')
          setTimeout(() => setNotifySent(false), 3000)
        },
        onError: (err) => setFormError(err.message),
      }
    )
  }

  const handleSaveEdits = () => {
    if (!tenant) return
    const data: { name?: string; bot_name?: string; customer_mode?: boolean } = {}
    if (editName.trim() !== tenant.name) data.name = editName.trim()
    if (editBotName.trim() !== tenant.bot_name) data.bot_name = editBotName.trim()
    if (Object.keys(data).length === 0) return
    updateTenant.mutate(
      { id: tenant.id, data },
      { onError: (err) => setFormError(err.message) }
    )
    setIsEditing(false)
  }

  const handleConvClick = (convId: string) => {
    setActiveConvId(activeConvId === convId ? null : convId)
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
            {isEditing ? (
              <div className="flex flex-wrap items-end gap-3 w-full">
                <div className="flex-1 min-w-[200px]">
                  <label className="mb-1 block text-xs font-medium text-ink-soft">Nombre del negocio</label>
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="h-10 text-sm"
                    placeholder="Nombre del negocio"
                  />
                </div>
                <div className="flex-1 min-w-[200px]">
                  <label className="mb-1 block text-xs font-medium text-ink-soft">Nombre del bot</label>
                  <Input
                    value={editBotName}
                    onChange={(e) => setEditBotName(e.target.value)}
                    className="h-10 text-sm"
                    placeholder="Nombre del bot"
                  />
                </div>
                <Button size="sm" onClick={handleSaveEdits} disabled={updateTenant.isLoading}>
                  {updateTenant.isLoading ? 'Guardando…' : 'Guardar'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setIsEditing(false)}>
                  Cancelar
                </Button>
              </div>
            ) : (
              <>
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
                <Button size="sm" variant="ghost" onClick={() => setIsEditing(true)}>
                  Editar
                </Button>
              </>
            )}
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

        {/* Tabs navigation */}
        <div className="border-t border-linen-100 pt-4">
          <div className="flex gap-1 mb-4">
            <button
              className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === 'info'
                  ? 'bg-brass text-brass-deep'
                  : 'bg-linen-100 text-ink-soft hover:bg-linen-200'
              }`}
              onClick={() => setActiveTab('info')}
            >
              Información
            </button>
            <button
              className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === 'contacts'
                  ? 'bg-brass text-brass-deep'
                  : 'bg-linen-100 text-ink-soft hover:bg-linen-200'
              }`}
              onClick={() => setActiveTab('contacts')}
            >
              Contactos del dueño
            </button>
            <button
              className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === 'conversations'
                  ? 'bg-brass text-brass-deep'
                  : 'bg-linen-100 text-ink-soft hover:bg-linen-200'
              }`}
              onClick={() => setActiveTab('conversations')}
            >
              Conversaciones
            </button>
          </div>

          {/* Tab: Información (contenido original) */}
          {activeTab === 'info' && (
            <>
              {/* Servicios del negocio */}
              <div>
                <h3 className="plate-label mb-2">Servicios de este negocio</h3>
                <div className="max-h-48 space-y-1.5 overflow-y-auto pr-1">
                  {tenant.modules.map((module: TenantModuleView) => (
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
                <div className="mt-4">
                  <h3 className="plate-label mb-2">Métodos de pago</h3>
                  {tenant.payment_methods.map((pm: TenantPaymentMethod) => (
                    <p key={pm.id} className="text-sm text-ink-soft">
                      {pm.brand} •••• {pm.last4}
                      {pm.is_default ? ' · principal' : ''}
                    </p>
                  ))}
                </div>
              )}

              {/* Actividad y facturación */}
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-linen-100 pt-4">
                <div className="rounded-md bg-linen-50 p-3">
                  <div className="plate-label mb-2">Actividad reciente</div>
                  <div className="space-y-1 text-sm text-ink-soft">
                    <p>
                      Último mensaje:{' '}
                      {tenant.last_message_at
                        ? formatDate(tenant.last_message_at)
                        : '—'}
                    </p>
                    <p>
                      Última cotización:{' '}
                      {tenant.last_quote_at
                        ? formatDate(tenant.last_quote_at)
                        : '—'}
                    </p>
                  </div>
                </div>
                <div className="rounded-md bg-linen-50 p-3">
                  <div className="plate-label mb-2">Facturación (cotizaciones)</div>
                  <div className="space-y-1 text-sm text-ink-soft">
                    <p>
                      Total histórico:{' '}
                      <span className="font-semibold text-ink">
                        ${tenant.total_quotes_amount.toLocaleString('es-CO')}
                      </span>
                    </p>
                    <p>
                      Últimos 30 días:{' '}
                      <span className="font-semibold text-ink">
                        {tenant.quotes_last_30d} cotizaciones
                      </span>
                    </p>
                  </div>
                </div>
              </div>

              {/* Acciones */}
              <div className="mt-4 flex flex-col gap-4 border-t border-linen-100 pt-4">
                <div className="flex flex-wrap items-end gap-3">
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

                {/* Notificar al negocio */}
                <div className="rounded-md bg-linen-50 p-3">
                  <label className="plate-label mb-2">Notificar a este negocio (WhatsApp)</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={notifyMsg}
                      onChange={(e) => setNotifyMsg(e.target.value)}
                      placeholder="Escribe el mensaje que recibirá el dueño..."
                      className="flex-1 h-11 rounded-md border border-linen-300 bg-panel px-3 text-sm text-ink"
                      disabled={sendAdminMsg.isLoading}
                    />
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleNotify}
                      disabled={sendAdminMsg.isLoading || !notifyMsg.trim() || !tenant?.wa_id}
                    >
                      {sendAdminMsg.isLoading ? 'Enviando…' : notifySent ? '✅ Enviado' : 'Enviar por WhatsApp'}
                    </Button>
                  </div>
                  {!tenant?.wa_id && (
                    <p className="mt-1 text-xs text-lacre">
                      ⚠️ Este negocio no tiene WhatsApp registrado. Ve a la pestaña "Conexión" o edita el negocio.
                    </p>
                  )}
                  {notifySent && (
                    <p className="mt-1 text-xs text-ok">Mensaje enviado al WhatsApp del dueño.</p>
                  )}
                </div>
              </div>
            </>
          )}

          {/* Tab: Contactos del dueño */}
          {activeTab === 'contacts' && (
            <div className="space-y-4">
              {/* Search & pagination */}
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex-1 min-w-[200px]">
                  <label className="mb-1 block text-xs font-medium text-ink-soft">Buscar contactos</label>
                  <Input
                    value={contactSearch}
                    onChange={(e) => {
                      setContactSearch(e.target.value)
                      setContactPage(0)
                    }}
                    placeholder="Nombre o teléfono..."
                    className="h-10 text-sm"
                  />
                </div>
                <div className="flex items-center gap-2 text-sm text-ink-soft">
                  {contactsData && (
                    <>
                      <span>Total: {contactsData.total}</span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setContactPage(p => Math.max(0, p - 1))}
                        disabled={contactPage === 0 || contactsLoading}
                      >
                        Anterior
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => contactsData && setContactPage(p => p + 1)}
                        disabled={
                          contactsLoading ||
                          !contactsData ||
                          (contactPage + 1) * 20 >= contactsData.total
                        }
                      >
                        Siguiente
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {/* Contactos list */}
              {contactsLoading ? (
                <div className="space-y-2">
                  <div className="skel h-14 w-full" />
                  <div className="skel h-14 w-full" />
                  <div className="skel h-14 w-full" />
                </div>
              ) : contactsData && contactsData.items.length === 0 ? (
                <p className="py-8 text-center text-sm text-linen-600">
                  No hay contactos registrados en este negocio.
                </p>
              ) : contactsData && (
                <div className="divide-y divide-linen-100">
                  {contactsData.items.map((contact) => (
                    <div
                      key={contact.id}
                      className={`flex flex-wrap items-center gap-3 py-3 cursor-pointer transition-colors ${
                        activeContactId === contact.id ? 'bg-linen-50' : ''
                      }`}
                      onClick={() => setActiveContactId(activeContactId === contact.id ? null : contact.id)}
                    >
                      <div className="min-w-[160px] flex-1">
                        <div className="text-sm font-medium text-ink">
                          {contact.name || 'Sin nombre'}
                        </div>
                        <div className="tabular text-xs text-linen-600">
                          {contact.wa_id} · {contact.messages_count} mensajes · {contact.interactions_count} interacciones
                        </div>
                        {contact.tags && contact.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {contact.tags.map((tag: string) => (
                              <span key={tag} className="text-xs px-2 py-0.5 rounded bg-brass/20 text-brass-deep">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium ${
                          contact.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
                        }`}
                      >
                        {contact.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                      {activeContactId === contact.id && <span className="text-brass">▼</span>}
                    </div>
                  ))}
                </div>
              )}

              {/* Contact detail + messages */}
              {activeContactId && (
                <div className="mt-4 rounded-md bg-linen-50 p-3 border border-linen-200">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-ink">
                      {contactDetailLoading ? 'Cargando…' : contactDetail?.name || 'Detalle del contacto'}
                    </h4>
                    <Button size="sm" variant="ghost" onClick={() => setActiveContactId(null)}>
                      Cerrar
                    </Button>
                  </div>

                  {contactDetail && !contactDetailLoading && (
                    <div className="space-y-2 text-sm text-ink-soft mb-4">
                      <p><b>Teléfono:</b> {contactDetail.wa_id}</p>
                      <p><b>Email:</b> {contactDetail.email || '—'}</p>
                      <p><b>Dirección:</b> {contactDetail.address || '—'}</p>
                      <p><b>Notas:</b> {contactDetail.notes || '—'}</p>
                      <p><b>Etiquetas:</b> {contactDetail.tags?.join(', ') || '—'}</p>
                      <p><b>Creado:</b> {formatDate(contactDetail.created_at)}</p>
                      <p><b>Última interacción:</b> {contactDetail.last_interaction_at ? formatDate(contactDetail.last_interaction_at) : '—'}</p>
                    </div>
                  )}

                  {/* Messages of this contact */}
                  {contactMsgLoading ? (
                    <div className="space-y-2">
                      <div className="skel h-10 w-full" />
                      <div className="skel h-10 w-full" />
                      <div className="skel h-10 w-full" />
                    </div>
                  ) : contactMsgData && contactMsgData.items.length === 0 ? (
                    <p className="text-center text-sm text-linen-600 py-4">Sin mensajes</p>
                  ) : contactMsgData && (
                    <div className="max-h-96 overflow-y-auto space-y-2">
                      {contactMsgData.items.map((msg: any) => (
                        <div
                          key={msg.id}
                          className={`flex gap-2 ${
                            msg.direction === 'in' ? 'flex-row' : 'flex-row-reverse'
                          }`}
                        >
                          <div
                            className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${
                              msg.direction === 'in'
                                ? 'bg-linen-100 text-ink'
                                : 'bg-brass/20 text-brass-deep'
                            }`}
                          >
                            <div className="flex items-center gap-1 text-xs text-linen-500 mb-1">
                              <span>{msg.direction === 'in' ? '👤 Cliente' : '🤖 Bot'}</span>
                              <span>{formatDate(msg.created_at)}</span>
                              <span className="text-[10px] uppercase">{msg.type}</span>
                            </div>
                            <div className="whitespace-pre-wrap break-words">
                              {msg.content || '<archivo>'}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab: Conversaciones (contenido original) */}
          {activeTab === 'conversations' && (
            <div>
              <h3 className="plate-label mb-3">Conversaciones con el bot</h3>
              {!reason.trim() ? (
                <div className="rounded-md bg-linen-50 p-4">
                  <p className="text-sm text-ink-soft mb-3">
                    Para ver el historial de conversaciones (Ley 1581 - Habeas Data), indica el motivo:
                  </p>
                  <div className="flex gap-2">
                    <Input
                      value={reason}
                      onChange={(e) => {
                        setReason(e.target.value)
                        setReasonError('')
                      }}
                      placeholder="Ej: Seguimiento comercial, auditoría, soporte..."
                      className="flex-1 h-10"
                      onKeyDown={(e) => e.key === 'Enter' && reason.trim() && refetchConvs()}
                    />
                    <Button size="sm" onClick={() => reason.trim() && refetchConvs()} disabled={!reason.trim()}>
                      Ver conversaciones
                    </Button>
                  </div>
                  {reasonError && <p className="mt-1 text-xs text-lacre">{reasonError}</p>}
                </div>
              ) : convLoading ? (
                <div className="space-y-2">
                  <div className="skel h-14 w-full" />
                  <div className="skel h-14 w-full" />
                  <div className="skel h-14 w-full" />
                </div>
              ) : convData && convData.items.length === 0 ? (
                <p className="py-4 text-center text-sm text-linen-600">
                  No hay conversaciones registradas.
                </p>
              ) : convData && (
                <div className="divide-y divide-linen-100">
                  {convData.items.map((conv: AdminConversation) => (
                    <div
                      key={conv.id}
                      className={`flex flex-wrap items-center gap-3 py-3 cursor-pointer transition-colors ${
                        activeConvId === conv.id ? 'bg-linen-50' : ''
                      }`}
                      onClick={() => handleConvClick(conv.id)}
                    >
                      <div className="min-w-[140px] flex-1">
                        <div className="text-sm font-medium text-ink">
                          {conv.contact_name || 'Sin nombre'}
                        </div>
                        <div className="tabular text-xs text-linen-600">
                          {conv.contact_wa_id} · {conv.messages_count} mensajes
                        </div>
                      </div>
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium ${
                          conv.status === 'open'
                            ? 'bg-ok-wash text-ok'
                            : 'bg-linen-100 text-linen-600'
                        }`}
                      >
                        {conv.status === 'open' ? 'Abierta' : conv.status}
                      </span>
                      <span className="text-xs text-linen-600 ml-auto">
                        {conv.last_message_at ? formatDate(conv.last_message_at) : '—'}
                      </span>
                      <span className="text-linen-400">▼</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Mensajes de la conversación seleccionada */}
              {activeConvId && convData && (
                <div className="mt-4 rounded-md bg-linen-50 p-3 border border-linen-200">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium text-ink">Mensajes</h4>
                    <Button size="sm" variant="ghost" onClick={() => setActiveConvId(null)}>
                      Cerrar
                    </Button>
                  </div>
                  {msgLoading ? (
                    <div className="space-y-2">
                      <div className="skel h-10 w-full" />
                      <div className="skel h-10 w-full" />
                      <div className="skel h-10 w-full" />
                    </div>
                  ) : msgData && msgData.items.length === 0 ? (
                    <p className="text-center text-sm text-linen-600 py-4">Sin mensajes</p>
                  ) : msgData && (
                    <div className="max-h-96 overflow-y-auto space-y-2">
                      {msgData.items.map((msg: AdminMessage) => (
                        <div
                          key={msg.id}
                          className={`flex gap-2 ${
                            msg.direction === 'in' ? 'flex-row' : 'flex-row-reverse'
                          }`}
                        >
                          <div
                            className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${
                              msg.direction === 'in'
                                ? 'bg-linen-100 text-ink'
                                : 'bg-brass/20 text-brass-deep'
                            }`}
                          >
                            <div className="flex items-center gap-1 text-xs text-linen-500 mb-1">
                              <span>{msg.direction === 'in' ? '👤 Cliente' : '🤖 Bot'}</span>
                              <span>{formatDate(msg.created_at)}</span>
                              <span className="text-[10px] uppercase">{msg.type}</span>
                            </div>
                            <div className="whitespace-pre-wrap break-words">
                              {msg.content || '<archivo>'}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
        </div>
      )}
    </Modal>
  )
}

function ClientsSection() {
  const { data, isLoading, error } = useAdminTenants()
  const updateStatus = useUpdateAdminTenantStatus()
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
              <Button
                type="button"
                variant={tenant.is_active ? 'destructive' : 'default'}
                size="sm"
                disabled={updateStatus.isLoading}
                onClick={() => {
                  const action = tenant.is_active ? 'bloquear' : 'desbloquear'
                  if (window.confirm(`¿Quieres ${action} a ${tenant.name}?`)) {
                    updateStatus.mutate({ id: tenant.id, isActive: !tenant.is_active })
                  }
                }}
              >
                {tenant.is_active ? 'Bloquear' : 'Desbloquear'}
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
  const { data: stats } = usePlatformAdminStats()

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
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Clientes registrados</h1>
        <p className="mt-1 text-sm text-linen-600">
          Personas y negocios que completaron el registro de Aura. Gestiona su
          plan, estado, actividad y servicios usados. El Mini CRM de cada cliente
          permanece separado.
        </p>
      </div>

      {stats && (
        <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            ['Clientes', stats.total_tenants],
            ['Activos', stats.active_tenants],
            ['Bloqueados', stats.blocked_tenants],
            ['Mensajes', stats.total_messages],
          ].map(([label, value]) => (
            <Card key={String(label)} className="p-4">
              <div className="text-xs uppercase tracking-wider text-linen-600">{label}</div>
              <div className="mt-1 text-2xl font-semibold tabular text-ink">{value}</div>
            </Card>
          ))}
        </div>
      )}

      {stats && stats.services.length > 0 && (
        <Card className="mb-5 p-5">
          <h2 className="mb-1 text-sm font-semibold text-ink">Servicios más utilizados</h2>
          <p className="mb-4 text-xs text-linen-600">
            Métrica global de clientes registrados, no del Mini CRM.
          </p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {stats.services.slice(0, 6).map((service) => (
              <div key={service.key} className="flex items-center justify-between rounded-lg bg-linen-50 px-3 py-2">
                <span className="text-sm text-ink">{service.name}</span>
                <span className="tabular text-xs text-linen-600">{service.interactions} usos · {service.tenants} clientes</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      <ClientsSection />
    </div>
  )
}
