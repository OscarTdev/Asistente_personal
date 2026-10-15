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
  PlanPrice,
  Quote,
  QuoteCreatePayload,
  QuoteItem,
  QuoteItemPayload,
  QuoteItemUpdatePayload,
  QuotePage,
  QuoteUpdatePayload,
  WhatsappConnectResult,
  WhatsappStatus,
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

// ── Modules ──────────────────────────────────────────────────────────────────

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

// ── Catalog ──────────────────────────────────────────────────────────────────

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

// ── Quotes ──────────────────────────────────────────────────────────────────

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

// ── Clientes (contactos de WhatsApp) ─────────────────────────────────────────

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

// ── Mini CRM: etiquetas, notas y cotizaciones por cliente ───────────────────

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

// ── Dashboard ──────────────────────────────────────────────────────────────

export function fetchDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/dashboard/stats')
}

// ── Planes y precios (admin de plataforma) ───────────────────────────────────

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

// ── Branding (logo del negocio en los PDFs) ─────────────────────────────────

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

// ── WhatsApp (conexión) ─────────────────────────────────────────────────────

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

// ── Seguimiento de cotizaciones ─────────────────────────────────────────────

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