// Data hooks for the panel dashboard metrics.

import { useQuery } from '@tanstack/react-query'
import { fetchDashboardStats } from '../lib/api'
import { DashboardStats } from '../types'

export function useDashboardStats() {
  return useQuery<DashboardStats, Error>({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardStats,
    refetchInterval: 30_000, // el mostrador se mantiene al día solo
  })
}
