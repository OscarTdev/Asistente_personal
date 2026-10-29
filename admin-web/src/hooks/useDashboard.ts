// Data hooks for the panel dashboard metrics.

import { useQuery } from '@tanstack/react-query'
import { fetchDashboardStats, fetchRealtimeActivity } from '../lib/api'
import { DashboardStats, RealtimeActivity } from '../types'

export function useDashboardStats() {
  return useQuery<DashboardStats, Error>({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardStats,
    refetchInterval: 30_000, // el mostrador se mantiene al día solo
  })
}

export function useRealtimeActivity() {
  return useQuery<RealtimeActivity, Error>({
    queryKey: ['dashboard', 'realtime'],
    queryFn: fetchRealtimeActivity,
    refetchInterval: 15_000,
  })
}
