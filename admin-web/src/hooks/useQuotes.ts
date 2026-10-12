// Data hooks for quotes, quote items and AI extraction.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addQuoteItem,
  createQuote,
  deleteQuoteItem,
  extractQuoteItems,
  fetchQuote,
  fetchQuotes,
  updateQuote,
  updateQuoteItem,
} from '../lib/api'
import {
  ExtractResponse,
  Quote,
  QuoteCreatePayload,
  QuoteItem,
  QuoteItemPayload,
  QuoteItemUpdatePayload,
  QuotePage,
  QuoteUpdatePayload,
} from '../types'

export interface QuotesParams {
  skip: number
  limit: number
  status: string
}

export function useQuotes(params: QuotesParams) {
  return useQuery<QuotePage, Error>({
    queryKey: ['quotes', params],
    queryFn: () => fetchQuotes(params),
    keepPreviousData: true,
  })
}

export function useQuote(id: string) {
  return useQuery<Quote, Error>({
    queryKey: ['quote', id],
    queryFn: () => fetchQuote(id),
    enabled: Boolean(id),
  })
}

export function useCreateQuote() {
  const queryClient = useQueryClient()
  return useMutation<Quote, Error, QuoteCreatePayload>({
    mutationFn: createQuote,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
    },
  })
}

export function useUpdateQuote(quoteId: string) {
  const queryClient = useQueryClient()
  return useMutation<Quote, Error, QuoteUpdatePayload>({
    mutationFn: (data) => updateQuote(quoteId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] })
    },
  })
}

export function useAddQuoteItem(quoteId: string) {
  const queryClient = useQueryClient()
  return useMutation<QuoteItem, Error, QuoteItemPayload>({
    mutationFn: (data) => addQuoteItem(quoteId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] })
    },
  })
}

export function useUpdateQuoteItem(quoteId: string) {
  const queryClient = useQueryClient()
  return useMutation<QuoteItem, Error, { itemId: string; data: QuoteItemUpdatePayload }>({
    mutationFn: ({ itemId, data }) => updateQuoteItem(quoteId, itemId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] })
    },
  })
}

export function useDeleteQuoteItem(quoteId: string) {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (itemId) => deleteQuoteItem(quoteId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quotes'] })
      queryClient.invalidateQueries({ queryKey: ['quote', quoteId] })
    },
  })
}

export function useExtractItems() {
  return useMutation<ExtractResponse, Error, string>({
    mutationFn: extractQuoteItems,
  })
}
