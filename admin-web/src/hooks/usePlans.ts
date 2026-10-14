// Data hooks for platform plan prices (admin panel).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchPlanPrices, updatePlanPrice } from '../lib/api'
import { PlanPrice } from '../types'

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
