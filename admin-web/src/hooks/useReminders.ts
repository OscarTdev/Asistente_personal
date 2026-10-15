// Data hooks for the reminders agenda (bot-delivered by WhatsApp).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createReminder, fetchReminders, setReminderStatus } from '../lib/api'
import { Reminder } from '../types'

export function useReminders(statusFilter?: string) {
  return useQuery<Reminder[], Error>({
    queryKey: ['reminders', statusFilter ?? 'all'],
    queryFn: () => fetchReminders(statusFilter),
    refetchInterval: 30000, // la agenda se refresca sola
  })
}

export function useCreateReminder() {
  const queryClient = useQueryClient()
  return useMutation<Reminder, Error, { content: string; remindAt: string }>({
    mutationFn: (data) => createReminder(data.content, data.remindAt),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] })
    },
  })
}

export function useSetReminderStatus() {
  const queryClient = useQueryClient()
  return useMutation<
    Reminder,
    Error,
    { id: string; status: 'done' | 'cancelled' }
  >({
    mutationFn: (data) => setReminderStatus(data.id, data.status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reminders'] })
    },
  })
}
