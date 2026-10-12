// Data hooks for the clients (WhatsApp contacts) API.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deactivateContact, fetchContact, fetchContacts, updateContact } from '../lib/api'
import { Contact, ContactDetail, ContactPage, ContactUpdatePayload } from '../types'

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
