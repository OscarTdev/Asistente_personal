// Clientes del asistente: quiénes escriben al bot, su última interacción y
// su ficha editable (nombre, notas, retirar/reactivar).

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/ui/card'
import Input from '../components/ui/input'
import Modal from '../components/ui/modal'
import Button from '../components/ui/button'
import Switch from '../components/ui/switch'
import ErrorSlip from '../components/ui/error-slip'
import { IconArrowLeft, IconPerson, IconX } from '../components/ui/icons'
import {
  useContact,
  useContactMessages,
  useContactNotes,
  useContactQuotes,
  useContacts,
  useContactTags,
  useCreateContactNote,
  useDeactivateContact,
  useDeleteContactNote,
  useUpdateContact,
} from '../hooks/useContacts'
import { formatDate } from '../lib/format'
import { Contact, ContactMessage, ContactUpdatePayload } from '../types'

const TYPE_MARKERS: Record<string, string> = {
  audio: '🎤 Nota de voz',
  image: '📷 Imagen',
  document: '📄 Documento',
}

function typeBadge(type: string): string {
  return type === 'text' ? '' : ` · ${TYPE_MARKERS[type] ?? type}`
}

function messageBody(message: ContactMessage): string {
  const text = message.content?.trim()
  if (text) return text
  return TYPE_MARKERS[message.type] ?? '(sin contenido)'
}

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
  const chat = useContactMessages(contactId)
  const chatRef = useRef<HTMLDivElement>(null)
  const notesQuery = useContactNotes(contactId)
  const createNote = useCreateContactNote(contactId)
  const deleteNote = useDeleteContactNote(contactId)
  const quotesQuery = useContactQuotes(contactId)
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [email, setEmail] = useState('')
  const [address, setAddress] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [newTag, setNewTag] = useState('')
  const [newNote, setNewNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // Al abrir la ficha (primera página cargada): mostrar lo más reciente abajo
  useEffect(() => {
    const el = chatRef.current
    if (
      el &&
      chat.data &&
      chat.data.pages.length === 1 &&
      chat.data.pages[0].items.length > 0
    ) {
      el.scrollTop = el.scrollHeight
    }
  }, [chat.data])

  useEffect(() => {
    if (contact) {
      setName(contact.name ?? '')
      setNotes(contact.notes ?? '')
      setEmail(contact.email ?? '')
      setAddress(contact.address ?? '')
      setTags(contact.tags ?? [])
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
      tags,
      email: email.trim() || null,
      address: address.trim() || null,
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

  const handleAddTag = () => {
    const tag = newTag.trim().toLowerCase()
    if (tag && !tags.includes(tag) && tags.length < 10) {
      setTags([...tags, tag])
    }
    setNewTag('')
  }

  const handleAddNote = () => {
    const content = newNote.trim()
    if (!content) return
    createNote.mutate(content, {
      onSuccess: () => setNewNote(''),
      onError: (err) => setFormError(err.message),
    })
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

          {/* Edición (mini CRM) */}
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
                Notas generales
              </label>
              <Input
                id="contact-notes"
                value={notes}
                onChangeValue={setNotes}
                placeholder="Ej: cliente de Laureles, paga puntual"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="contact-email">
                Correo
              </label>
              <Input
                id="contact-email"
                value={email}
                onChangeValue={setEmail}
                placeholder="cliente@correo.com"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="contact-address">
                Dirección
              </label>
              <Input
                id="contact-address"
                value={address}
                onChangeValue={setAddress}
                placeholder="Calle 10 #43-21, Laureles"
              />
            </div>
          </div>

          {/* Etiquetas */}
          <div>
            <h3 className="plate-label mb-2">Etiquetas</h3>
            <div className="flex flex-wrap items-center gap-2">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 rounded-full bg-pine-wash px-2.5 py-1 text-xs font-medium text-pine"
                >
                  {tag}
                  <button
                    type="button"
                    aria-label={`Quitar etiqueta ${tag}`}
                    className="text-pine/70 hover:text-lacre"
                    onClick={() => setTags(tags.filter((t) => t !== tag))}
                  >
                    <IconX className="h-3 w-3" />
                  </button>
                </span>
              ))}
              <div className="flex items-center gap-1">
                <Input
                  value={newTag}
                  onChangeValue={setNewTag}
                  placeholder="Nueva etiqueta…"
                  aria-label="Nueva etiqueta"
                  className="h-8 w-32"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleAddTag()
                    }
                  }}
                />
                <Button type="button" variant="outline" size="sm" onClick={handleAddTag}>
                  Agregar
                </Button>
              </div>
              <span className="text-xs text-linen-600">
                (se guardan con «Guardar cambios»)
              </span>
            </div>
          </div>

          {/* Cotizaciones del cliente */}
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="plate-label">Cotizaciones</h3>
              <span className="tabular text-xs text-linen-600">
                {quotesQuery.data?.length ?? 0} en total
              </span>
            </div>
            {quotesQuery.isLoading ? (
              <div className="skel h-12 w-full" />
            ) : (quotesQuery.data?.length ?? 0) === 0 ? (
              <p className="text-xs text-linen-600">Sin cotizaciones todavía.</p>
            ) : (
              <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                {quotesQuery.data?.map((quote) => (
                  <div key={quote.id} className="ficha flex items-center gap-3 px-3 py-2">
                    <span
                      className={`rounded-full px-2 py-1 text-xs font-medium ${
                        quote.status === 'accepted'
                          ? 'bg-ok-wash text-ok'
                          : quote.status === 'sent'
                            ? 'bg-brass/20 text-brass-deep'
                            : 'bg-linen-100 text-linen-600'
                      }`}
                    >
                      {quote.status}
                    </span>
                    <span className="tabular text-sm font-medium text-ink">
                      ${quote.total.toLocaleString('es-CO')}
                    </span>
                    <time className="ml-auto tabular text-xs text-linen-600">
                      {formatDate(quote.created_at)}
                    </time>
                    <a
                      href={`/cotizador/cotizaciones/${quote.id}`}
                      className="rounded px-2 py-1 text-sm font-medium text-pine hover:bg-pine-wash"
                    >
                      Ver
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Notas del cliente (timeline) */}
          <div>
            <h3 className="plate-label mb-2">Notas del cliente</h3>
            <div className="mb-3 flex gap-2">
              <Input
                value={newNote}
                onChangeValue={setNewNote}
                placeholder="Ej: 14/oct: pidió mantenimiento del tablero"
                aria-label="Nueva nota del cliente"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleAddNote()
                  }
                }}
              />
              <Button
                type="button"
                size="sm"
                onClick={handleAddNote}
                disabled={createNote.isLoading || !newNote.trim()}
              >
                {createNote.isLoading ? 'Guardando…' : 'Agregar nota'}
              </Button>
            </div>
            {notesQuery.error && <ErrorSlip message={notesQuery.error.message} />}
            {notesQuery.isLoading ? (
              <div className="skel h-12 w-full" />
            ) : (notesQuery.data?.length ?? 0) === 0 ? (
              <p className="text-xs text-linen-600">
                Sin notas. Las que tomes aquí y por chat se verán en la ficha.
              </p>
            ) : (
              <div className="max-h-40 space-y-2 overflow-y-auto pr-1">
                {notesQuery.data?.map((note) => (
                  <div key={note.id} className="ficha px-3 py-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <time className="tabular text-xs text-linen-600">
                        {formatDate(note.created_at)}
                      </time>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm('¿Borrar esta nota?')) {
                            deleteNote.mutate(note.id, {
                              onError: (err) => setFormError(err.message),
                            })
                          }
                        }}
                        className="text-xs font-medium text-lacre hover:underline disabled:opacity-50"
                        disabled={deleteNote.isLoading}
                      >
                        Borrar
                      </button>
                    </div>
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-ink-soft">
                      {note.content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Historial de conversación */}
          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="plate-label">Historial de conversación</h3>
              {chat.data && (
                <span className="tabular text-xs text-linen-600">
                  {chat.data.pages[0]?.total ?? 0} mensajes
                </span>
              )}
            </div>
            {chat.error && <ErrorSlip message={chat.error.message} />}
            <div ref={chatRef} className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {chat.isLoading ? (
                <div className="skel h-20 w-full" />
              ) : (chat.data?.pages[0]?.total ?? 0) === 0 ? (
                <p className="text-xs text-linen-600">
                  Aún no hay mensajes registrados de este cliente.
                </p>
              ) : (
                <>
                  {chat.hasPreviousPage && (
                    <div className="flex justify-center pb-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => chat.fetchPreviousPage()}
                        disabled={chat.isFetchingPreviousPage}
                      >
                        {chat.isFetchingPreviousPage ? 'Cargando…' : 'Cargar anteriores'}
                      </Button>
                    </div>
                  )}
                  {[...(chat.data?.pages ?? [])]
                    .flatMap((page) => page.items)
                    .reverse()
                    .map((message) => (
                      <div
                        key={message.id}
                        className={`flex ${message.direction === 'out' ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={`max-w-[78%] rounded-lg px-3 py-2 ${
                            message.direction === 'out'
                              ? 'bg-pine text-[#f4f1e9]'
                              : 'border border-linen-200 bg-panel'
                          }`}
                        >
                          <div className="flex items-baseline justify-between gap-3">
                            <span
                              className={`text-[0.6875rem] font-semibold uppercase tracking-[0.09em] ${
                                message.direction === 'out'
                                  ? 'text-linen-300'
                                  : 'text-linen-600'
                              }`}
                            >
                              {message.direction === 'out' ? 'Aura' : 'Cliente'}
                              {typeBadge(message.type)}
                            </span>
                            <time className="tabular text-[0.6875rem] opacity-70">
                              {formatDate(message.created_at)}
                            </time>
                          </div>
                          <p className="mt-0.5 whitespace-pre-wrap break-words text-sm">
                            {messageBody(message)}
                          </p>
                        </div>
                      </div>
                    ))}
                </>
              )}
            </div>
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
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined)
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
    tag: tagFilter,
  })
  const updateContact = useUpdateContact()
  const { data: availableTags } = useContactTags()

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
      <Link
        to="/servicios"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-pine hover:underline"
      >
        <IconArrowLeft className="h-4 w-4" />
        Servicios
      </Link>

      {/* Desk header */}
      <div className="mt-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Contactos y clientes</h1>
        <p className="mt-1 text-sm text-linen-600">
          El mini CRM del negocio: quiénes son tus clientes, su historial de
          conversación, cotizaciones, notas y etiquetas.
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
        {(availableTags?.length ?? 0) > 0 && (
          <label className="flex items-center gap-2 text-sm text-ink-soft">
            Etiqueta
            <select
              value={tagFilter ?? ''}
              onChange={(e) => {
                setTagFilter(e.target.value || undefined)
                setPage(0)
              }}
              className="h-11 rounded-md border border-linen-300 bg-panel px-2 text-sm text-ink"
              aria-label="Filtrar por etiqueta"
            >
              <option value="">Todas</option>
              {availableTags?.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </label>
        )}
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
                        <div>
                          {contact.name ?? 'Sin nombre'}
                          {(contact.tags?.length ?? 0) > 0 && (
                            <div className="mt-0.5 flex flex-wrap gap-1">
                              {contact.tags.map((tag) => (
                                <span
                                  key={tag}
                                  className="rounded-full bg-pine-wash px-1.5 py-0.5 text-[0.625rem] font-medium text-pine"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
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
