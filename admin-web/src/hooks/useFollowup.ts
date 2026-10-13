// Data hooks for the quote follow-up service.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchFollowupPending, runFollowupNow } from '../lib/api'
import { FollowUpPendingPage, FollowUpRunResult } from '../types'

export function useFollowupPending(skip: number = 0, limit: number = 20) {
  return useQuery<FollowUpPendingPage, Error>({
    queryKey: ['followup-pending', skip, limit],
    queryFn: () => fetchFollowupPending(skip, limit),
  })
}

export function useRunFollowup() {
  const queryClient = useQueryClient()
  return useMutation<FollowUpRunResult, Error>({
    mutationFn: runFollowupNow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['followup-pending'] })
    },
  })
}
