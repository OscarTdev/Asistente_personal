// Data hooks de la conexión Google del dueño (Mi negocio → Conectar Google).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  authorizeGoogle,
  disconnectGoogle,
  fetchGmailSummary,
  fetchGoogleStatus,
  googleCallback,
} from '../lib/api'
import { GmailSummaryItem, GoogleCallbackResult, GoogleStatus } from '../types'

export function useGoogleStatus() {
  return useQuery<GoogleStatus, Error>({
    queryKey: ['google', 'status'],
    queryFn: fetchGoogleStatus,
  })
}

export function useGoogleAuthorize() {
  return useMutation<{ authorization_url: string }, Error, void>({
    mutationFn: () => authorizeGoogle(),
  })
}

export function useGoogleCallback() {
  const queryClient = useQueryClient()
  return useMutation<GoogleCallbackResult, Error, { code: string; state: string }>({
    mutationFn: ({ code, state }) => googleCallback(code, state),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['google'] })
    },
  })
}

export function useGoogleDisconnect() {
  const queryClient = useQueryClient()
  return useMutation<{ disconnected: boolean }, Error, void>({
    mutationFn: () => disconnectGoogle(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['google'] })
    },
  })
}

// Prueba de la conexión desde Mi negocio: los 3 correos más recientes
export function useGmailTest(enabled: boolean) {
  return useQuery<GmailSummaryItem[], Error>({
    queryKey: ['google', 'gmail-test'],
    queryFn: () => fetchGmailSummary(3),
    enabled,
  })
}
