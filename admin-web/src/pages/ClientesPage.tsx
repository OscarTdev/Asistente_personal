// Clientes del asistente: quiénes escriben al bot, su última interacción y
// su ficha editable (nombre, notas, retirar/reactivar).

import { useEffect, useState } from 'react'
import Card from '../components/ui/card'
import Input from '../components/ui/input'
import Modal from '../components/ui/modal'
import Button from '../components/ui/button'
import Switch from '../components/ui/switch'
import ErrorSlip from '../components/ui/error-slip'
import { IconPerson } from '../components/ui/icons'
import {
  useContact,
  useContacts,
  useDeactivateContact,
  useUpdateContact,
} from '../hooks/useContacts'
import { formatDate } from '../lib/format'
import { Contact, ContactUpdatePayload } from '../types'

const PAGE_SIZE = 10

// ── Ficha del cliente ────────────────────────────────────────────────────────

function ContactFicha({
  contactId,
  onClose,
}: {
  contactId: string
  onClose: () => void
}) {
  const { data: contact, isLoading, error } = useContact(contactId)
  const updateContact = useUpdateContact()
  const deactivateContact = useDeactivateContact()
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (contact) {
      setName(contact.name ?? '')
      setNotes(contact.notes ?? '')
      setFormError(null)
    }
  }, [contact])

  const handleSave = () => {
    if (!contact) {
      return
    }
    const data: ContactUpdatePayload = {
      name: name.trim() || null,
      notes: notes.trim() || null,
    }
    setSaving(true)
    updateContact.mutate(
      { id: contact.id, data },
      {
        onSuccess: () => setSaving(false),
        onError: (err) => {
          setSaving(false)
          setFormError(err.message)
        },
      }
    )
  }

  const handleToggleActive = () => {
    if (!contact) {
      return
    }
    const nextActive = !contact.is_active
    if (!nextActive && !window.confirm(`¿Retirar a ${contact.name ?? contact.wa_id}? Su historial se conserva.`)) {
      return
    }
    updateContact.mutate(
      { id: contact.id, data: { is_active: nextActive } },
      {
        onSuccess: () => setSaving(false),
        onError: (err) => setFormError(err.message),
      }
    )
  }

  return (
    <Modal open onClose={onClose} title="Ficha del cliente" wide>
      {isLoading && (
        <div className="space-y-3">
          <div className="skel h-5 w-1/2" />
          <div className="skel h-4 w-1/3" />
          <div className="skel h-24 w-full" />
        </div>
      )}
      {error && <ErrorSlip message={error.message} />}
      {contact && (
        <div className="space-y-5">
          {/* Identidad */}
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-pine-wash text-pine">
              <IconPerson className="h-5 w-5" />
            </span>
            <div>
              <div className="text-base font-semibold text-ink">
                {contact.name ?? 'Sin nombre'}
              </div>
              <div className="tabular text-xs text-linen-600">WhatsApp {contact.wa_id}</div>
            </div>
            <span
              className={`ml-auto rounded-full px-2 py-1 text-xs font-medium ${
                contact.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
              }`}
            >
              {contact.is_active ? 'Activo' : 'Retirado'}
            </span>
          </div>

          {/* Datos del mostrador */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Mensajes</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {contact.messages_count}
              </div>
            </div>
            <div className="rounded-md bg-linen-50 p-3">
              <div className="plate-label">Interacciones</div>
              <div className="tabular mt-0.5 text-lg font-semibold text-ink">
                {contact.interactions_count}
              </div>
            </div>
            <div className="col-span-2 rounded-md bg-linen-50 p-3">
              <div className="plate-label">Desde</div>
              <div className="tabular mt-0.5 text-sm font-medium text-ink">
                {formatDate(contact.created_at)}
              </div>
            </div>
          </div>

          {/* Edición */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="contact-name">
                Nombre
              </label>
              <Input
                id="contact-name"
                value={name}
                onChangeValue={setName}
                placeholder="Como lo conoce el negocio"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="contact-notes">
                Notas
              </label>
              <Input
                id="contact-notes"
                value={notes}
                onChangeValue={setNotes}
                placeholder="Ej: cliente de Laureles, paga puntual"
              />
            </div>
          </div>

          {/* Mensajes recientes */}
          <div>
            <h3 className="plate-label mb-2">Mensajes recientes</h3>
            {contact.recent_messages.length === 0 ? (
              <p className="text-xs text-linen-600">
                Aún no hay mensajes registrados de este cliente.
              </p>
            ) : (
              <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
                {contact.recent_messages.map((message) => (
                  <div key={message.id} className="ficha px-3 py-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="plate-label">
                        {message.direction === 'in' ? 'Recibido' : 'Enviado'}
                        {message.type !== 'text' ? ` · ${message.type}` : ''}
                      </span>
                      <time className="tabular text-xs text-linen-600">
                        {formatDate(message.created_at)}
                      </time>
                    </div>
                    <p className="mt-0.5 truncate text-sm text-ink-soft">
                      {message.content ?? '(sin contenido)'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {formError && <ErrorSlip message={formError} />}

          <div className="flex items-center justify-between border-t border-linen-100 pt-4">
            {/* Destructive action kept apart, outline style */}
            <Button
              type="button"
              variant="outline"
              onClick={handleToggleActive}
              disabled={saving || updateContact.isLoading}
              className={
                contact.is_active ? 'border-lacre/40 text-lacre hover:bg-lacre-wash' : ''
              }
            >
              {contact.is_active ? 'Retirar cliente' : 'Reactivar cliente'}
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onClose}>
                Cerrar
              </Button>
              <Button type="button" onClick={handleSave} disabled={saving || updateContact.isLoading}>
                {saving ? 'Guardando…' : 'Guardar cambios'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function ClientesPage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showRetired, setShowRetired] = useState(false)
  const [page, setPage] = useState(0)
  const [openId, setOpenId] = useState<string | null>(null)
  const [heldIds, setHeldIds] = useState<Set<string>>(new Set())

  // Debounce the search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const { data, isLoading, error } = useContacts({
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    search: debouncedSearch,
    activeOnly: !showRetired,
  })
  const updateContact = useUpdateContact()

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const hold = (id: string) => {
    setHeldIds((previous) => new Set(previous).add(id))
  }
  const release = (id: string) => {
    setHeldIds((previous) => {
      const next = new Set(previous)
      next.delete(id)
      return next
    })
  }

  const handleToggleActive = (contact: Contact) => {
    const nextActive = !contact.is_active
    if (!nextActive && !window.confirm(`¿Retirar a ${contact.name ?? contact.wa_id}? Su historial se conserva.`)) {
      return
    }
    updateContact.mutate(
      { id: contact.id, data: { is_active: nextActive } },
      { onSuccess: () => hold(contact.id) }
    )
  }

  return (
    <div>
      {/* Desk header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Clientes</h1>
        <p className="mt-1 text-sm text-linen-600">
          Quiénes escriben al asistente, su última interacción y su ficha.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="w-full max-w-xs">
          <Input
            value={search}
            onChangeValue={(value) => setSearch(value)}
            placeholder="Buscar por nombre o celular…"
            aria-label="Buscar clientes"
          />
        </div>
        <label className="flex items-center gap-2.5 text-sm text-ink-soft">
          <Switch checked={showRetired} onChange={setShowRetired} label="Mostrar clientes retirados" />
          Mostrar retirados
        </label>
      </div>

      {/* Errors as persistent errata slips */}
      <div className="mb-4">
        <ErrorSlip message={error?.message ?? updateContact.error?.message ?? null} />
      </div>

      {/* The client list */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-linen-100">
            {[0, 1, 2, 3, 4, 5].map((index) => (
              <div key={index} className="flex h-12 items-center gap-4 px-4">
                <div className="skel h-4 w-1/4" />
                <div className="skel h-4 w-20" />
                <div className="skel ml-auto h-4 w-24" />
              </div>
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  <th className="plate-label px-4 py-3 font-semibold">Nombre</th>
                  <th className="plate-label px-4 py-3 font-semibold">Celular</th>
                  <th className="plate-label px-4 py-3 font-semibold">Última interacción</th>
                  <th className="plate-label px-4 py-3 font-semibold">Mensajes</th>
                  <th className="plate-label px-4 py-3 font-semibold">Estado</th>
                  <th className="plate-label px-4 py-3 text-right font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((contact) => (
                  <tr
                    key={contact.id}
                    className={`border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50 ${
                      heldIds.has(contact.id) ? 'row-hold' : ''
                    }`}
                    onMouseEnter={() => release(contact.id)}
                    onFocus={() => release(contact.id)}
                  >
                    <td className="px-4 py-3 font-medium text-ink">
                      <div className="flex items-center gap-2.5">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-pine-wash text-pine">
                          <IconPerson className="h-4 w-4" />
                        </span>
                        {contact.name ?? 'Sin nombre'}
                      </div>
                    </td>
                    <td className="tabular px-4 py-3 text-ink-soft">{contact.wa_id}</td>
                    <td className="tabular px-4 py-3 text-ink-soft">
                      {formatDate(contact.last_interaction_at)}
                    </td>
                    <td className="tabular px-4 py-3 text-ink-soft">{contact.messages_count}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded-full ${
                          contact.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
                        }`}
                      >
                        {contact.is_active ? 'Activo' : 'Retirado'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setOpenId(contact.id)}
                        className="rounded px-2 py-1.5 text-sm font-medium text-pine hover:bg-pine-wash"
                      >
                        Abrir ficha
                      </button>
                      {/* Destructive action kept apart, outline style */}
                      <button
                        type="button"
                        onClick={() => handleToggleActive(contact)}
                        disabled={updateContact.isLoading}
                        className="ml-3 rounded border border-lacre/40 px-2.5 py-1.5 text-sm font-medium text-lacre hover:bg-lacre-wash disabled:opacity-50"
                      >
                        {contact.is_active ? 'Retirar' : 'Reactivar'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : debouncedSearch.trim().length > 0 ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-medium text-ink">Ningún cliente coincide con esa búsqueda</p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
              Pruebe con otro nombre o celular, o limpie la búsqueda para verlos todos.
            </p>
            <div className="mt-4 flex justify-center">
              <Button type="button" variant="outline" onClick={() => setSearch('')}>
                Limpiar búsqueda
              </Button>
            </div>
          </div>
        ) : (
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-medium text-ink">Todavía no hay clientes</p>
            <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
              Cuando alguien escriba al WhatsApp del asistente, su ficha aparecerá aquí
              automáticamente con su primera conversación.
            </p>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.items.length > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-linen-600">
          <span className="tabular">
            Página {page + 1} de {totalPages} · {data.total} clientes
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              Anterior
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))}
              disabled={page + 1 >= totalPages}
            >
              Siguiente
            </Button>
          </div>
        </div>
      )}

      {/* Ficha modal */}
      {openId && <ContactFicha contactId={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}
