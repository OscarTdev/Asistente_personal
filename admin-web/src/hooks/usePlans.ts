// Data hooks for platform plan prices (admin panel).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchPlanEntitlements,
  fetchPlanPrices,
  updatePlanEntitlement,
  updatePlanPrice,
} from '../lib/api'
import { PlanEntitlementItem, PlanPrice } from '../types'

export function usePlanPrices() {
  return useQuery<PlanPrice[], Error>({
    queryKey: ['plan-prices'],
    queryFn: fetchPlanPrices,
  })
}

export function useUpdatePlanPrice() {
  const queryClient = useQueryClient()
  return useMutation<PlanPrice, Error, { plan: string; priceCop: number }>({
    mutationFn: (data) => updatePlanPrice(data.plan, data.priceCop),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan-prices'] })
    },
  })
}

export function usePlanEntitlements() {
  return useQuery<PlanEntitlementItem[], Error>({
    queryKey: ['plan-entitlements'],
    queryFn: fetchPlanEntitlements,
  })
}

export function useUpdatePlanEntitlement() {
  const queryClient = useQueryClient()
  return useMutation<
    { plan: string; module_key: string; allowed: boolean },
    Error,
    { plan: string; moduleKey: string; allowed: boolean }
  >({
    mutationFn: (data) =>
      updatePlanEntitlement(data.plan, data.moduleKey, data.allowed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan-entitlements'] })
      queryClient.invalidateQueries({ queryKey: ['admin-tenants'] })
    },
  })
}
