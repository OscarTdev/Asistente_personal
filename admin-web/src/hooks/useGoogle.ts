// Data hooks de la conexión Google del dueño (Mi negocio → Conectar Google).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  authorizeGoogle,
  disconnectGoogle,
  fetchGoogleStatus,
  googleCallback,
} from '../lib/api'
import { GoogleCallbackResult, GoogleStatus } from '../types'

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
