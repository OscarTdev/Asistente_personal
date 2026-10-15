// Data hooks for the platform owner's clients (tenants) in the Admin panel.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  changeAdminTenantPlan,
  createTenantCheckoutLink,
  fetchAdminTenant,
  fetchAdminTenants,
  TenantCheckoutResult,
} from '../lib/api'
import { TenantDetail, TenantSummary } from '../types'

export function useAdminTenants() {
  return useQuery<TenantSummary[], Error>({
    queryKey: ['admin-tenants'],
    queryFn: fetchAdminTenants,
  })
}

export function useAdminTenant(id: string | null) {
  return useQuery<TenantDetail, Error>({
    queryKey: ['admin-tenant', id],
    queryFn: () => fetchAdminTenant(id as string),
    enabled: Boolean(id),
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
