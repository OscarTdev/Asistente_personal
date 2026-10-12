// Data hooks for the tenant modules API.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchModules, toggleModule } from '../lib/api'
import { Module } from '../types'

export function useModules() {
  return useQuery<Module[], Error>({
    queryKey: ['modules'],
    queryFn: fetchModules,
  })
}

export function useToggleModule() {
  const queryClient = useQueryClient()
  return useMutation<Module, Error, { moduleKey: string; isEnabled: boolean }>({
    mutationFn: ({ moduleKey, isEnabled }) => toggleModule(moduleKey, isEnabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['modules'] })
    },
  })
}
