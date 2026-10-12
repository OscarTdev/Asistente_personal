// Data hooks for the price catalog API.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCatalogItem,
  deleteCatalogItem,
  fetchCatalog,
  importCatalogCsv,
  updateCatalogItem,
} from '../lib/api'
import {
  CatalogImportResult,
  CatalogItem,
  CatalogItemPayload,
  CatalogItemUpdatePayload,
  CatalogPage,
} from '../types'

export interface CatalogParams {
  skip: number
  limit: number
  search: string
  activeOnly: boolean
}

export function useCatalog(params: CatalogParams) {
  return useQuery<CatalogPage, Error>({
    queryKey: ['catalog', params],
    queryFn: () =>
      fetchCatalog({
        skip: params.skip,
        limit: params.limit,
        search: params.search,
        activeOnly: params.activeOnly,
      }),
    keepPreviousData: true,
  })
}

export function useCreateCatalogItem() {
  const queryClient = useQueryClient()
  return useMutation<CatalogItem, Error, CatalogItemPayload>({
    mutationFn: createCatalogItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useUpdateCatalogItem() {
  const queryClient = useQueryClient()
  return useMutation<CatalogItem, Error, { id: string; data: CatalogItemUpdatePayload }>({
    mutationFn: ({ id, data }) => updateCatalogItem(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useDeleteCatalogItem() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: deleteCatalogItem,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}

export function useImportCatalogCsv() {
  const queryClient = useQueryClient()
  return useMutation<CatalogImportResult, Error, File>({
    mutationFn: importCatalogCsv,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog'] })
    },
  })
}
