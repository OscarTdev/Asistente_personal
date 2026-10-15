export interface User {
  id: string
  email: string
  full_name: string | null
  role: string
  tenant_id: string
  bot_name: string
  is_platform_admin: boolean
}

export interface PlanPrice {
  plan: string
  label: string
  price_cop: number
  is_overridden: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

export interface FeedEvent {
  id: string
  type: string
  tenant_id: string
  created_at: string
  data: {
    message_id?: string
    conversation_id?: string
    contact_id?: string
    contact_wa_id?: string
    push_name?: string | null
    direction?: string
    preview?: string | null
  }
}

export type WsStatus = "connecting" | "open" | "closed"

export interface Module {
  key: string
  name: string
  description: string | null
  category: string
  is_enabled: boolean
  is_custom: boolean
  dev_status: 'active' | 'development'
  workspace: string | null
  parent: string | null
}

export interface CatalogItem {
  id: string
  tenant_id: string
  name: string
  description: string | null
  unit: string | null
  unit_price: string
  is_active: boolean
}

export interface CatalogPage {
  items: CatalogItem[]
  total: number
  skip: number
  limit: number
}

export interface QuoteItem {
  id: string
  quote_id: string
  catalog_item_id: string | null
  description: string
  quantity: string
  unit_price: string
  line_total: string
  position: number
}

export interface Quote {
  id: string
  tenant_id: string
  contact_id: string | null
  conversation_id: string | null
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired'
  total: string
  notes: string | null
  valid_until: string | null
  created_at: string
  updated_at: string
  items?: QuoteItem[]
}

export interface QuotePage {
  items: Quote[]
  total: number
  skip: number
  limit: number
}

export interface ExtractedSuggestion {
  description: string
  quantity: string | number
  catalog_item_id: string | null
  catalog_name: string | null
  unit_price: string | null
  unit: string | null
  matched: boolean
}

export interface ExtractResponse {
  suggestions: ExtractedSuggestion[]
  raw_extraction: any[]
}

// ── Payloads (frontend → backend) ──────────────────────────────────────────

export interface CatalogItemPayload {
  name: string
  description?: string | null
  unit?: string | null
  unit_price: number
}

export interface CatalogItemUpdatePayload {
  name?: string
  description?: string | null
  unit?: string | null
  unit_price?: number
  is_active?: boolean
}

export interface CatalogImportResult {
  created: number
  updated: number
  errors: string[]
}

export interface QuoteItemPayload {
  description: string
  quantity: number
  unit_price: number
  catalog_item_id?: string | null
  position?: number
}

export interface QuoteItemUpdatePayload {
  description?: string
  quantity?: number
  unit_price?: number
  position?: number
}

export interface QuoteCreatePayload {
  contact_id?: string | null
  conversation_id?: string | null
  notes?: string | null
  valid_until?: string | null
  items: QuoteItemPayload[]
}

export interface QuoteUpdatePayload {
  status?: string
  notes?: string | null
  valid_until?: string | null
}

// ── Clientes (contactos de WhatsApp) ───────────────────────────────────────

export interface Contact {
  id: string
  wa_id: string
  name: string | null
  notes: string | null
  is_active: boolean
  created_at: string
  last_interaction_at: string | null
  messages_count: number
  interactions_count: number
  tags: string[]
  email: string | null
  address: string | null
}

export interface ContactPage {
  items: Contact[]
  total: number
  skip: number
  limit: number
}

export interface ContactMessage {
  id: string
  direction: string
  type: string
  content: string | null
  created_at: string
}

export interface ContactDetail extends Contact {
  recent_messages: ContactMessage[]
}

export interface ContactMessagesPage {
  items: ContactMessage[]
  total: number
  skip: number
  limit: number
}

export interface ContactUpdatePayload {
  name?: string | null
  notes?: string | null
  is_active?: boolean
  tags?: string[] | null
  email?: string | null
  address?: string | null
}

export interface ContactNote {
  id: string
  content: string
  created_at: string
}

export interface Reminder {
  id: string
  content: string
  remind_at: string
  status: string
  sent_at: string | null
  created_at: string
}

export interface Branding {
  has_logo: boolean
  logo_data_url: string | null
}

// ── Mis clientes (negocios con el asistente) — panel Admin ───────────────────

export interface TenantSummary {
  id: string
  name: string
  slug: string
  bot_name: string
  is_active: boolean
  plan: string
  plan_label: string
  plan_price_cop: number
  wa_id: string | null
  account_type: string
  nit: string | null
  customer_mode: boolean
  subscription_status: string | null
  subscription_period_end: string | null
  enabled_modules: number
  total_modules: number
  contacts: number
  quotes: number
  messages: number
  users: number
}

export interface TenantModuleView {
  key: string
  name: string
  category: string
  dev_status: string
  is_enabled: boolean
  entitled: boolean
}

export interface TenantPaymentMethod {
  id: string
  provider: string
  brand: string
  last4: string
  exp_month: number | null
  exp_year: number | null
  is_default: boolean
}

export interface TenantSubscription {
  plan_key: string
  status: string
  provider: string
  current_period_end: string | null
}

export interface TenantDetail extends TenantSummary {
  modules: TenantModuleView[]
  payment_methods: TenantPaymentMethod[]
  subscription: TenantSubscription | null
}

// ── Dashboard ──────────────────────────────────────────────────────────────

export interface ServiceStat {
  key: string
  name: string
  dev_status: 'active' | 'development'
  is_enabled: boolean
  interactions: number
  interactions_7d: number
}

export interface DashboardStats {
  bot_name: string
  contacts: {
    total: number
    active_last_7d: number
  }
  quotes: {
    total: number
    last_7d: number
    by_status: Record<string, number>
  }
  services: ServiceStat[]
  messages_last_7d: number
}

// ── WhatsApp (conexión) ─────────────────────────────────────────────────────

export interface WhatsappStatus {
  state: string
  instance: string
}

export interface WhatsappConnectResult {
  base64?: string
  code?: string
  pairingCode?: string
  qrcode?: { code?: string }
  instance?: { state?: string }
}

// ── Seguimiento de cotizaciones ─────────────────────────────────────────────

export interface FollowUpPendingItem {
  quote_id: string
  contact_name: string | null
  contact_wa_id: string
  total: string
  sent_at: string
  days_elapsed: number
  round1_sent_at: string | null
  round2_sent_at: string | null
  replied: boolean
}

export interface FollowUpPendingPage {
  items: FollowUpPendingItem[]
  total: number
}

export interface FollowUpRunResult {
  round1_sent: number
  round2_sent: number
  errors: number
}