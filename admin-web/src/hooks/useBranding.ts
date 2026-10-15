// Data hooks for the business branding (logo shown on PDFs).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteBrandingLogo, fetchBranding, uploadBrandingLogo } from '../lib/api'
import { Branding } from '../types'

export function useBranding() {
  return useQuery<Branding, Error>({
    queryKey: ['branding'],
    queryFn: fetchBranding,
  })
}

export function useUploadBrandingLogo() {
  const queryClient = useQueryClient()
  return useMutation<{ has_logo: boolean; logo_mimetype: string }, Error, File>({
    mutationFn: uploadBrandingLogo,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['branding'] })
    },
  })
}

export function useDeleteBrandingLogo() {
  const queryClient = useQueryClient()
  return useMutation<void, Error>({
    mutationFn: () => deleteBrandingLogo(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['branding'] })
    },
  })
}
