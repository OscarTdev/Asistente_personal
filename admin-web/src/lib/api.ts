import {
  CatalogImportResult,
  CatalogItem,
  CatalogItemPayload,
  CatalogItemUpdatePayload,
  CatalogPage,
  Branding,
  Contact,
  ContactDetail,
  ContactMessagesPage,
  ContactNote,
  ContactPage,
  ContactUpdatePayload,
  DashboardStats,
  ExtractResponse,
  FollowUpPendingPage,
  FollowUpRunResult,
  LoginResponse,
  Module,
  PlanEntitlementItem,
  PlanPrice,
  Quote,
  QuoteCreatePayload,
  QuoteItem,
  QuoteItemPayload,
  QuoteItemUpdatePayload,
  QuotePage,
  QuoteUpdatePayload,
  Reminder,
  TenantDetail,
  TenantSummary,
  WhatsappConnectResult,
  WhatsappStatus,
  AdminTenant,
  AdminTenantDetail,
  AdminModule,
  AdminConversation,
  AdminMessage,
  CheckoutLinkResult,
  ChannelIdentity,
} from '../types'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('asistente_token')
  if (!token) {
    return {}
  }
  return {
    Authorization: `Bearer ${token}`,
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      ...init.headers,
      ...authHeaders(),
    },
  })

  if (!response.ok) {
    let errorMessage = 'Error desconocido'
    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorData.message || 'Error desconocido'
    } catch (e) {
      // Ignore
    }
    throw new ApiError(errorMessage, response.status)
  }

  // 204 No Content: successful DELETE calls have no body
  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export async function loginRequest(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  })
}

// â”€â”€ Modules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchModules(): Promise<Module[]> {
  return apiFetch<Module[]>('/modules')
}

export function toggleModule(moduleKey: string, isEnabled: boolean): Promise<Module> {
  return apiFetch<Module>(`/modules/${encodeURIComponent(moduleKey)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_enabled: isEnabled }),
  })
}

// â”€â”€ Catalog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface CatalogQuery {
  skip: number
  limit: number
  search?: string
  activeOnly: boolean
}

export function fetchCatalog(query: CatalogQuery): Promise<CatalogPage> {
  const params = new URLSearchParams({
    skip: String(query.skip),
    limit: String(query.limit),
    active_only: String(query.activeOnly),
  })
  if (query.search) {
    params.set('search', query.search)
  }
  return apiFetch<CatalogPage>(`/catalog?${params.toString()}`)
}

export function createCatalogItem(data: CatalogItemPayload): Promise<CatalogItem> {
  return apiFetch<CatalogItem>('/catalog', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateCatalogItem(id: string, data: CatalogItemUpdatePayload): Promise<CatalogItem> {
  return apiFetch<CatalogItem>(`/catalog/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteCatalogItem(id: string): Promise<void> {
  return apiFetch<void>(`/catalog/${id}`, { method: 'DELETE' })
}

export function importCatalogCsv(file: File): Promise<CatalogImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  // No Content-Type header here: the browser sets the multipart boundary.
  return apiFetch<CatalogImportResult>('/catalog/import-csv', {
    method: 'POST',
    body: formData,
  })
}

// â”€â”€ Quotes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface QuotesQuery {
  skip: number
  limit: number
  status?: string
}

export function fetchQuotes(query: QuotesQuery): Promise<QuotePage> {
  const params = new URLSearchParams({
    skip: String(query.skip),
    limit: String(query.limit),
  })
  if (query.status) {
    params.set('status', query.status)
  }
  return apiFetch<QuotePage>(`/quotes?${params.toString()}`)
}

export function fetchQuote(id: string): Promise<Quote> {
  return apiFetch<Quote>(`/quotes/${id}`)
}

export function createQuote(data: QuoteCreatePayload): Promise<Quote> {
  return apiFetch<Quote>('/quotes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateQuote(id: string, data: QuoteUpdatePayload): Promise<Quote> {
  return apiFetch<Quote>(`/quotes/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function extractQuoteItems(text: string): Promise<ExtractResponse> {
  return apiFetch<ExtractResponse>('/quotes/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export function addQuoteItem(quoteId: string, data: QuoteItemPayload): Promise<QuoteItem> {
  return apiFetch<QuoteItem>(`/quotes/${quoteId}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function updateQuoteItem(
  quoteId: string,
  itemId: string,
  data: QuoteItemUpdatePayload
): Promise<QuoteItem> {
  return apiFetch<QuoteItem>(`/quotes/${quoteId}/items/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deleteQuoteItem(quoteId: string, itemId: string): Promise<void> {
  return apiFetch<void>(`/quotes/${quoteId}/items/${itemId}`, { method: 'DELETE' })
}

// â”€â”€ Clientes (contactos de WhatsApp) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export interface ContactsQuery {
  skip: number
  limit: number
  search?: string
  activeOnly: boolean
  tag?: string
}

export function fetchContacts(query: ContactsQuery): Promise<ContactPage> {
  const params = new URLSearchParams({
    skip: String(query.skip),
    limit: String(query.limit),
    active_only: String(query.activeOnly),
  })
  if (query.search) {
    params.set('search', query.search)
  }
  if (query.tag) {
    params.set('tag', query.tag)
  }
  return apiFetch<ContactPage>(`/contacts?${params.toString()}`)
}

export function fetchContact(id: string): Promise<ContactDetail> {
  return apiFetch<ContactDetail>(`/contacts/${id}`)
}

export function fetchContactMessages(
  id: string,
  skip: number,
  limit: number
): Promise<ContactMessagesPage> {
  const params = new URLSearchParams({
    skip: String(skip),
    limit: String(limit),
  })
  return apiFetch<ContactMessagesPage>(`/contacts/${id}/messages?${params.toString()}`)
}

// â”€â”€ Mini CRM: etiquetas, notas y cotizaciones por cliente â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchContactTags(): Promise<string[]> {
  return apiFetch<string[]>('/contacts/tags')
}

export function fetchContactNotes(id: string): Promise<ContactNote[]> {
  return apiFetch<ContactNote[]>(`/contacts/${id}/notes`)
}

export function createContactNote(
  id: string,
  content: string
): Promise<ContactNote> {
  return apiFetch<ContactNote>(`/contacts/${id}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export function deleteContactNote(contactId: string, noteId: string): Promise<void> {
  return apiFetch<void>(`/contacts/${contactId}/notes/${noteId}`, { method: 'DELETE' })
}

export interface ContactQuote {
  id: string
  status: string
  total: number
  created_at: string
}

export function fetchContactQuotes(id: string): Promise<ContactQuote[]> {
  return apiFetch<ContactQuote[]>(`/contacts/${id}/quotes`)
}

// â”€â”€ Agenda (recordatorios) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchReminders(statusFilter?: string): Promise<Reminder[]> {
  const params = new URLSearchParams()
  if (statusFilter) {
    params.set('status', statusFilter)
  }
  const qs = params.toString()
  return apiFetch<Reminder[]>(`/reminders${qs ? `?${qs}` : ''}`)
}

export function createReminder(content: string, remindAt: string): Promise<Reminder> {
  return apiFetch<Reminder>('/reminders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, remind_at: remindAt }),
  })
}

export function setReminderStatus(
  id: string,
  status: 'done' | 'cancelled'
): Promise<Reminder> {
  return apiFetch<Reminder>(`/reminders/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
}

export function updateContact(
  id: string,
  data: ContactUpdatePayload
): Promise<Contact> {
  return apiFetch<Contact>(`/contacts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function deactivateContact(id: string): Promise<void> {
  return apiFetch<void>(`/contacts/${id}`, { method: 'DELETE' })
}

// â”€â”€ Dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/dashboard/stats')
}

// â”€â”€ Planes y precios (admin de plataforma) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchPlanPrices(): Promise<PlanPrice[]> {
  return apiFetch<PlanPrice[]>('/admin/plan-prices')
}

export function updatePlanPrice(plan: string, priceCop: number): Promise<PlanPrice> {
  return apiFetch<PlanPrice>(`/admin/plan-prices/${encodeURIComponent(plan)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ price_cop: priceCop }),
  })
}

// â”€â”€ Matriz gratis/VIP (servicios por plan) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchPlanEntitlements(): Promise<PlanEntitlementItem[]> {
  return apiFetch<PlanEntitlementItem[]>('/admin/plan-entitlements')
}

export function updatePlanEntitlement(
  plan: string,
  moduleKey: string,
  allowed: boolean
): Promise<{ plan: string; module_key: string; allowed: boolean }> {
  return apiFetch<{ plan: string; module_key: string; allowed: boolean }>(
    `/admin/plan-entitlements/${encodeURIComponent(plan)}/${encodeURIComponent(moduleKey)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allowed }),
    }
  )
}

// â”€â”€ Branding (logo del negocio en los PDFs) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchBranding(): Promise<Branding> {
  return apiFetch<Branding>('/branding')
}

export function uploadBrandingLogo(
  file: File
): Promise<{ has_logo: boolean; logo_mimetype: string }> {
  const formData = new FormData()
  formData.append('file', file)
  // Sin Content-Type: el navegador agrega el multipart boundary
  return apiFetch<{ has_logo: boolean; logo_mimetype: string }>('/branding/logo', {
    method: 'PUT',
    body: formData,
  })
}

export function deleteBrandingLogo(): Promise<void> {
  return apiFetch<void>('/branding/logo', { method: 'DELETE' })
}

// â”€â”€ Mis clientes (negocios con el asistente) â€” panel Admin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchAdminTenants(): Promise<TenantSummary[]> {
  return apiFetch<TenantSummary[]>('/admin/tenants')
}

export function fetchAdminTenant(id: string): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(`/admin/tenants/${id}`)
}

export function changeAdminTenantPlan(
  id: string,
  plan: string
): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(`/admin/tenants/${id}/plan`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan }),
  })
}

export interface TenantCheckoutResult {
  preference_id: string | null
  init_point: string
  plan: string
  price_cop: number
  whatsapp_sent: boolean
}

export function createTenantCheckoutLink(
  id: string
): Promise<TenantCheckoutResult> {
  return apiFetch<TenantCheckoutResult>(`/admin/tenants/${id}/checkout-link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
}

// â”€â”€ WhatsApp (conexiÃ³n) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function updateAdminTenant(
  id: string,
  data: { name?: string; bot_name?: string; customer_mode?: boolean }
): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(`/admin/tenants/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function fetchWhatsappStatus(): Promise<WhatsappStatus> {
  return apiFetch<WhatsappStatus>('/whatsapp/status')
}

export function connectWhatsapp(): Promise<WhatsappConnectResult> {
  return apiFetch<WhatsappConnectResult>('/whatsapp/connect', { method: 'POST' })
}

export function disconnectWhatsapp(): Promise<{ status: string; detail?: string }> {
  return apiFetch<{ status: string; detail?: string }>('/whatsapp/disconnect', {
    method: 'POST',
  })
}

export function testSendWhatsapp(number: string, text: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>('/whatsapp/test-send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ number, text }),
  })
}

// â”€â”€ Seguimiento de cotizaciones â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function fetchFollowupPending(
  skip: number = 0,
  limit: number = 20
): Promise<FollowUpPendingPage> {
  return apiFetch<FollowUpPendingPage>(
    `/followup/pending?skip=${skip}&limit=${limit}`
  )
}

export function runFollowupNow(): Promise<FollowUpRunResult> {
  return apiFetch<FollowUpRunResult>('/followup/run', { method: 'POST' })
}

export async function downloadQuotePdf(quoteId: string): Promise<void> {
  const response = await fetch(`/api/v1/quotes/${quoteId}/pdf`, { headers: authHeaders() })
  if (!response.ok) {
    let errorMessage = 'Error desconocido al generar el PDF'
    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorMessage
    } catch (e) {
      // Ignore non-JSON error bodies
    }
    throw new ApiError(errorMessage, response.status)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `cotizacion_${quoteId.slice(0, 8)}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function setAdminTenantWhatsapp(
  id: string,
  wa_id: string | null
): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(`/admin/tenants/${id}/whatsapp`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wa_id }),
  })
}

export function toggleAdminModule(
  tenantId: string,
  moduleKey: string,
  isEnabled: boolean
): Promise<void> {
  return apiFetch<void>(
    `/admin/tenants/${tenantId}/modules/${encodeURIComponent(moduleKey)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_enabled: isEnabled }),
    }
  )
}

export function fetchAdminConversations(
  tenantId: string,
  skip: number = 0,
  limit: number = 20
): Promise<{ items: any[]; total: number }> {
  return apiFetch<{ items: any[]; total: number }>(
    `/admin/tenants/${tenantId}/conversations?skip=${skip}&limit=${limit}`
  )
}

export function fetchAdminMessages(
  tenantId: string,
  conversationId: string,
  limit: number = 100
): Promise<{ items: any[]; total: number }> {
  return apiFetch<{ items: any[]; total: number }>(
    `/admin/tenants/${tenantId}/conversations/${conversationId}/messages?limit=${limit}`
  )
}

export function addAdminPaymentMethod(
  tenantId: string,
  data: { brand: string; last4: string; exp_month?: number; exp_year?: number }
): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(
    `/admin/tenants/${tenantId}/payment-method`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  )
}

export function deleteAdminPaymentMethod(
  tenantId: string,
  paymentMethodId: string
): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(
    `/admin/tenants/${tenantId}/payment-methods/${paymentMethodId}`,
    { method: 'DELETE' }
  )
}

export function fetchAdminIdentities(
  tenantId: string,
  contactId: string
): Promise<any[]> {
  return apiFetch<any[]>(
    `/admin/tenants/${tenantId}/contacts/${contactId}/identities`
  )
}

export function addAdminIdentity(
  tenantId: string,
  contactId: string,
  data: { channel: string; external_id: string; kind: string }
): Promise<any> {
  return apiFetch<any>(
    `/admin/tenants/${tenantId}/contacts/${contactId}/identities`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  )
}
