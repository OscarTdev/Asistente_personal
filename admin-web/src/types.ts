export interface User {
  id: string
  email: string
  full_name: string | null
  role: string
  tenant_id: string
  bot_name: string
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