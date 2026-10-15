// Data hooks for the clients (WhatsApp contacts) API.

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deactivateContact,
  fetchContact,
  fetchContactMessages,
  fetchContacts,
  updateContact,
} from '../lib/api'
import { Contact, ContactDetail, ContactMessagesPage, ContactPage, ContactUpdatePayload } from '../types'

export interface ContactsParams {
  skip: number
  limit: number
  search: string
  activeOnly: boolean
}

export function useContacts(params: ContactsParams) {
  return useQuery<ContactPage, Error>({
    queryKey: ['contacts', params],
    queryFn: () =>
      fetchContacts({
        skip: params.skip,
        limit: params.limit,
        search: params.search,
        activeOnly: params.activeOnly,
      }),
    keepPreviousData: true,
  })
}

export function useContact(id: string) {
  return useQuery<ContactDetail, Error>({
    queryKey: ['contact', id],
    queryFn: () => fetchContact(id),
    enabled: Boolean(id),
  })
}

const MESSAGES_PAGE_SIZE = 30

export function useContactMessages(contactId: string) {
  // Historial paginado: página 1 = los más recientes; "cargar anteriores"
  // trae páginas hacia atrás. Se muestra en orden cronológico.
  return useInfiniteQuery<ContactMessagesPage, Error>({
    queryKey: ['contact-messages', contactId],
    queryFn: (context) =>
      fetchContactMessages(contactId, Number(context.pageParam ?? 0), MESSAGES_PAGE_SIZE),
    getNextPageParam: (lastPage, allPages) => {
      const fetched = allPages.reduce((acc, page) => acc + page.items.length, 0)
      return fetched < lastPage.total ? fetched : undefined
    },
  })
}

export function useUpdateContact() {
  const queryClient = useQueryClient()
  return useMutation<Contact, Error, { id: string; data: ContactUpdatePayload }>({
    mutationFn: ({ id, data }) => updateContact(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contacts'] })
      queryClient.invalidateQueries({ queryKey: ['contact'] })
    },
  })
}

export function useDeactivateContact() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: deactivateContact,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contacts'] })
      queryClient.invalidateQueries({ queryKey: ['contact'] })
    },
  })
}
