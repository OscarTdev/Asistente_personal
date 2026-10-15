// Data hooks for the clients (WhatsApp contacts) API.

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createContactNote,
  deactivateContact,
  deleteContactNote,
  fetchContact,
  fetchContactMessages,
  fetchContactNotes,
  fetchContactQuotes,
  fetchContacts,
  updateContact,
} from '../lib/api'
import {
  Contact,
  ContactDetail,
  ContactMessagesPage,
  ContactNote,
  ContactPage,
  ContactUpdatePayload,
} from '../types'

export interface ContactsParams {
  skip: number
  limit: number
  search: string
  activeOnly: boolean
  tag?: string
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
        tag: params.tag,
      }),
    keepPreviousData: true,
  })
}

export function useContactTags() {
  return useQuery<string[], Error>({
    queryKey: ['contact-tags'],
    queryFn: () => import('../lib/api').then((m) => m.fetchContactTags()),
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

// ── Mini CRM ───────────────────────────────────────────────────────────────

export function useContactNotes(contactId: string) {
  return useQuery<ContactNote[], Error>({
    queryKey: ['contact-notes', contactId],
    queryFn: () => fetchContactNotes(contactId),
  })
}

export function useCreateContactNote(contactId: string) {
  const queryClient = useQueryClient()
  return useMutation<ContactNote, Error, string>({
    mutationFn: (content) => createContactNote(contactId, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-notes', contactId] })
      queryClient.invalidateQueries({ queryKey: ['contacts'] })
    },
  })
}

export function useDeleteContactNote(contactId: string) {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: (noteId) => deleteContactNote(contactId, noteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-notes', contactId] })
    },
  })
}

export function useContactQuotes(contactId: string) {
  return useQuery<import('../lib/api').ContactQuote[], Error>({
    queryKey: ['contact-quotes', contactId],
    queryFn: () => fetchContactQuotes(contactId),
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
