// Data hooks for the WhatsApp connection (status polling, QR, test send).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  connectWhatsapp,
  disconnectWhatsapp,
  fetchWhatsappStatus,
  testSendWhatsapp,
} from '../lib/api'
import { WhatsappConnectResult, WhatsappStatus } from '../types'

export function useWhatsappStatus() {
  return useQuery<WhatsappStatus, Error>({
    queryKey: ['whatsapp-status'],
    queryFn: fetchWhatsappStatus,
    refetchInterval: 5000, // el QR y el estado se refrescan solos
  })
}

export function useConnectWhatsapp() {
  return useMutation<WhatsappConnectResult, Error>({
    mutationFn: connectWhatsapp,
  })
}

export function useTestSendWhatsapp() {
  const queryClient = useQueryClient()
  return useMutation<{ status: string }, Error, { number: string; text: string }>({
    mutationFn: (data) => testSendWhatsapp(data.number, data.text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] })
    },
  })
}

export function useDisconnectWhatsapp() {
  const queryClient = useQueryClient()
  return useMutation<{ status: string; detail?: string }, Error>({
    mutationFn: disconnectWhatsapp,
    onSuccess: () => {
      // El estado pasa a "close": refrescar de inmediato, sin esperar el polling
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] })
    },
  })
}
