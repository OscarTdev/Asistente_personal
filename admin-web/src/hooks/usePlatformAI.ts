// Data hooks for the Platform AI configuration (super admin).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchPlatformAIConfig,
  updatePlatformAIConfig,
  type AIConfigItem,
  type AIConfigUpdate,
} from '../lib/api'

export function usePlatformAIConfig() {
  return useQuery<Record<string, AIConfigItem>, Error>({
    queryKey: ['platform-ai-config'],
    queryFn: fetchPlatformAIConfig,
    // No auto-refetch: el guardián notifica cambios por WhatsApp
  })
}

export function useUpdatePlatformAIConfig() {
  const queryClient = useQueryClient()
  return useMutation<AIConfigItem, Error, AIConfigUpdate & { key: string }>({
    mutationFn: ({ key, value }) => updatePlatformAIConfig(key, value),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platform-ai-config'] })
    },
  })
}