// Data hooks for the platform owner's clients (tenants) in the Admin panel.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  changeAdminTenantPlan,
  createTenantCheckoutLink,
  fetchAdminConversations,
  fetchAdminMessages,
  fetchAdminTenant,
  fetchAdminTenants,
  sendAdminMessageToTenant,
  updateAdminTenant,
  fetchAdminTenantContacts,
  fetchAdminTenantContact,
  fetchAdminTenantContactMessages,
  fetchPlatformAdminStats,
  updateAdminTenantStatus,
  TenantCheckoutResult,
} from '../lib/api'
import {
  TenantDetail,
  TenantSummary,
  AdminConversationPage,
  AdminMessagePage,
  TenantUpdatePayload,
  AdminTenantContactPage,
  AdminTenantContactDetail,
  AdminTenantContactMessagesPage,
  PlatformAdminStats,
} from '../types'

export function useAdminTenants() {
  return useQuery<TenantSummary[], Error>({
    queryKey: ['admin-tenants'],
    queryFn: fetchAdminTenants,
  })
}

export function usePlatformAdminStats() {
  return useQuery<PlatformAdminStats, Error>({
    queryKey: ['platform-admin-stats'],
    queryFn: fetchPlatformAdminStats,
  })
}

export function useUpdateAdminTenantStatus() {
  const queryClient = useQueryClient()
  return useMutation<TenantDetail, Error, { id: string; isActive: boolean }>({
    mutationFn: ({ id, isActive }) => updateAdminTenantStatus(id, isActive),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
      queryClient.invalidateQueries({ queryKey: ['admin-tenant', variables.id] })
      queryClient.invalidateQueries({ queryKey: ['platform-admin-stats'] })
    },
  })
}

export function useAdminTenant(id: string | null) {
  return useQuery<TenantDetail, Error>({
    queryKey: ['admin-tenant', id],
    queryFn: () => fetchAdminTenant(id as string),
    enabled: Boolean(id),
  })
}

export function useAdminConversations(tenantId: string | null, reason: string | null) {
  return useQuery<AdminConversationPage, Error>({
    queryKey: ['admin-conversations', tenantId, reason],
    queryFn: () => fetchAdminConversations(tenantId as string, 0, 50, reason || undefined),
    enabled: Boolean(tenantId && reason && reason.trim()),
  })
}

export function useAdminMessages(tenantId: string | null, conversationId: string | null) {
  return useQuery<AdminMessagePage, Error>({
    queryKey: ['admin-messages', tenantId, conversationId],
    queryFn: () => fetchAdminMessages(tenantId as string, conversationId as string),
    enabled: Boolean(tenantId && conversationId),
  })
}

export function useChangeTenantPlan() {
  const queryClient = useQueryClient()
  return useMutation<TenantDetail, Error, { id: string; plan: string }>({
    mutationFn: (data) => changeAdminTenantPlan(data.id, data.plan),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
      queryClient.invalidateQueries({ queryKey: ['admin-tenant', variables.id] })
    },
  })
}

export function useTenantCheckoutLink() {
  return useMutation<TenantCheckoutResult, Error, string>({
    mutationFn: (id) => createTenantCheckoutLink(id),
  })
}

export function useSendAdminMessage() {
  const queryClient = useQueryClient()
  return useMutation<{ message_id: string }, Error, { tenantId: string; message: string }>({
    mutationFn: (data) => sendAdminMessageToTenant(data.tenantId, data.message),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-tenant', variables.tenantId] })
    },
  })
}

export function useUpdateTenant() {
  const queryClient = useQueryClient()
  return useMutation<TenantDetail, Error, { id: string; data: TenantUpdatePayload }>({
    mutationFn: ({ id, data }) => updateAdminTenant(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
      queryClient.invalidateQueries({ queryKey: ['admin-tenant', variables.id] })
    },
  })
}

export function useAdminTenantContacts(
  tenantId: string | null,
  skip: number = 0,
  limit: number = 20,
  search?: string,
  activeOnly: boolean = true,
  tag?: string
) {
  return useQuery<AdminTenantContactPage, Error>({
    queryKey: ['admin-tenant-contacts', tenantId, skip, limit, search, activeOnly, tag],
    queryFn: () => fetchAdminTenantContacts(tenantId as string, skip, limit, search, activeOnly, tag),
    enabled: Boolean(tenantId),
  })
}

export function useAdminTenantContact(
  tenantId: string | null,
  contactId: string | null
) {
  return useQuery<AdminTenantContactDetail, Error>({
    queryKey: ['admin-tenant-contact', tenantId, contactId],
    queryFn: () => fetchAdminTenantContact(tenantId as string, contactId as string),
    enabled: Boolean(tenantId && contactId),
  })
}

export function useAdminTenantContactMessages(
  tenantId: string | null,
  contactId: string | null,
  skip: number = 0,
  limit: number = 30
) {
  return useQuery<AdminTenantContactMessagesPage, Error>({
    queryKey: ['admin-tenant-contact-messages', tenantId, contactId, skip, limit],
    queryFn: () => fetchAdminTenantContactMessages(tenantId as string, contactId as string, skip, limit),
    enabled: Boolean(tenantId && contactId),
  })
}
