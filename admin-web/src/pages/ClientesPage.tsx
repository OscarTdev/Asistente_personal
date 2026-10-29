// ClientesPage v3 — Mini CRM completo (smb-admin style)
// design-taste-frontend: list screen + detail screen, real data, no placeholders
// frontend-design: tokens, dark mode, shadcn/ui components
// ui-ux-pro-max: scanability, density, keyboard nav, focus visible

import { useEffect, useRef, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '@/auth/AuthContext'
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip"
import { Switch } from "@/components/ui/switch"
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from "@/components/ui/table"
import {
  IconArrowLeft,
  IconPerson,
  IconUsers,
  IconX,
  IconSearch,
  IconFilter,
  IconTag,
  IconMail,
  IconMapPin,
  IconMessageSquare,
  IconFileText,
  IconCalendar,
  IconTrash2,
  IconEdit,
  IconEye,
  IconMoreVertical,
  IconChevronDown,
  IconChevronUp,
  IconDownload,
} from "@/components/ui/icons"
import {
  useContacts,
  useContact,
  useContactMessages,
  useContactNotes,
  useContactQuotes,
  useContactTags,
  useCreateContactNote,
  useDeleteContactNote,
  useUpdateContact,
  useDeactivateContact,
} from '@/hooks/useContacts'
import { useGoogleContactsStatus, useImportGoogleContacts } from '@/hooks/useGoogle'
import { formatDate } from '@/lib/format'
import { Contact, ContactMessage, ContactNote, ContactUpdatePayload, ContactQuote } from '@/types'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20

const TYPE_MARKERS: Record<string, string> = {
  audio: 'Nota de voz',
  image: 'Imagen',
  document: 'Documento',
}

function typeBadge(type: string): string {
  return type === 'text' ? '' : ` · ${TYPE_MARKERS[type] ?? type}`
}

function messageBody(message: ContactMessage): string {
  const text = message.content?.trim()
  if (text) return text
  return TYPE_MARKERS[message.type] ?? '(sin contenido)'
}

function getInitials(name: string | null): string {
  if (!name) return '?'
  return name.trim().split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase()
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'accepted': return 'default'
    case 'sent': return 'secondary'
    case 'draft': return 'outline'
    case 'rejected':
    case 'expired': return 'destructive'
    default: return 'outline'
  }
}

// ── ContactFicha (Detail Screen - two column) ────────────────────────────────

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
  const [activeTab, setActiveTab] = useState<'info' | 'chat' | 'quotes' | 'notes'>('info')

  // Scroll to bottom on first load
  useEffect(() => {
    const el = chatRef.current
    if (el && chat.data && chat.data.pages.length === 1 && chat.data.pages[0].items.length > 0) {
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

  const handleSave = useCallback(() => {
    if (!contact) return
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
        onError: (err) => { setSaving(false); setFormError(err.message) },
      }
    )
  }, [contact, name, notes, tags, email, address, updateContact])

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
    if (!contact) return
    const nextActive = !contact.is_active
    if (!nextActive && !window.confirm(`¿Retirar a ${contact.name ?? contact.wa_id}? Su historial se conserva.`)) {
      return
    }
    updateContact.mutate(
      { id: contact.id, data: { is_active: nextActive } },
      { onError: (err) => setFormError(err.message) }
    )
  }

  return (
    <TooltipProvider>
      <Card className="w-full max-w-6xl animate-fade-in">
        <CardHeader className="pb-3 border-b" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <Avatar className="h-10 w-10">
                <AvatarImage src="" alt="" />
                <AvatarFallback className="text-sm font-semibold" style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)' }}>
                  {contact ? getInitials(contact.name) : '?'}
                </AvatarFallback>
              </Avatar>
              <div>
                <CardTitle className="text-lg" style={{ color: 'var(--color-ink)' }}>
                  {contact?.name ?? 'Sin nombre'}
                </CardTitle>
                <div className="text-xs" style={{ color: 'var(--color-ink-muted)' }}>
                  WhatsApp {contact?.wa_id}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={contact?.is_active ? 'default' : 'secondary'} className="text-xs">
                {contact?.is_active ? 'Activo' : 'Retirado'}
              </Badge>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="sm" onClick={onClose} aria-label="Cerrar ficha">
                    <IconX className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="left">Cerrar ficha</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </CardHeader>

        {isLoading && (
          <CardContent className="py-8">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="skel h-20 w-full" />
              <div className="skel h-20 w-full md:col-span-3" />
            </div>
          </CardContent>
        )}

        {error && (
          <CardContent className="py-4">
            <div className="slip" style={{ background: 'var(--color-danger-wash)', borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
              Error al cargar: {error.message}
            </div>
          </CardContent>
        )}

        {contact && !isLoading && !error && (
          <>
            {/* KPI Strip */}
            <CardContent className="pt-4 pb-2">
              <div className="kpi-strip stagger">
                <div className="kpi-card">
                  <span className="kpi-label">Mensajes</span>
                  <span className="kpi-value tabular">{contact.messages_count}</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Interacciones</span>
                  <span className="kpi-value tabular">{contact.interactions_count}</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Cotizaciones</span>
                  <span className="kpi-value tabular">{quotesQuery.data?.length ?? 0}</span>
                </div>
                <div className="kpi-card">
                  <span className="kpi-label">Desde</span>
                  <span className="kpi-value text-base font-medium" style={{ color: 'var(--color-ink-soft)' }}>
                    {formatDate(contact.created_at).split(' ')[0]}
                  </span>
                </div>
              </div>
            </CardContent>

            {/* Tabs for detail sections */}
            <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "quotes" | "notes" | "info" | "chat")} className="w-full">
              <TabsList className="list-tabs w-full border-b" style={{ borderColor: 'var(--color-border-default)' }}>
                <TabsTrigger value="info" className="list-tab px-4 py-2 text-sm font-medium">
                  Información
                </TabsTrigger>
                <TabsTrigger value="chat" className="list-tab px-4 py-2 text-sm font-medium">
                  Chat ({chat.data?.pages[0]?.total ?? 0})
                </TabsTrigger>
                <TabsTrigger value="quotes" className="list-tab px-4 py-2 text-sm font-medium">
                  Cotizaciones ({quotesQuery.data?.length ?? 0})
                </TabsTrigger>
                <TabsTrigger value="notes" className="list-tab px-4 py-2 text-sm font-medium">
                  Notas ({notesQuery.data?.length ?? 0})
                </TabsTrigger>
              </TabsList>

              <TabsContent value="info" className="pt-4 space-y-4 animate-fade-in">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="contact-name" className="text-xs font-medium" style={{ color: 'var(--color-ink-soft)' }}>Nombre</Label>
                    <Input
                      id="contact-name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Como lo conoce el negocio"
                      className="h-10"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="contact-email" className="text-xs font-medium" style={{ color: 'var(--color-ink-soft)' }}>Correo</Label>
                    <Input
                      id="contact-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="cliente@correo.com"
                      className="h-10"
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-2">
                    <Label htmlFor="contact-notes" className="text-xs font-medium" style={{ color: 'var(--color-ink-soft)' }}>Notas generales</Label>
                    <Input
                      id="contact-notes"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Ej: cliente de Laureles, paga puntual"
                      className="h-10"
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-2">
                    <Label htmlFor="contact-address" className="text-xs font-medium" style={{ color: 'var(--color-ink-soft)' }}>Dirección</Label>
                    <Input
                      id="contact-address"
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                      placeholder="Calle 10 #43-21, Laureles"
                      className="h-10"
                    />
                  </div>
                </div>

                {/* Tags */}
                <div className="space-y-3">
                  <Label className="text-xs font-medium" style={{ color: 'var(--color-ink-soft)' }}>Etiquetas</Label>
                  <div className="flex flex-wrap items-center gap-2">
                    {tags.map((tag: string) => (
                      <Badge key={tag} variant="secondary" className="gap-1 text-xs">
                        {tag}
                        <button
                          type="button"
                          onClick={() => setTags(tags.filter((t) => t !== tag))}
                          className="hover:text-destructive focus-visible:outline-none"
                          aria-label={`Quitar etiqueta ${tag}`}
                        >
                          <IconX className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                    <div className="flex items-center gap-1">
                      <Input
                        value={newTag}
                        onChange={(e) => setNewTag(e.target.value)}
                        placeholder="Nueva etiqueta…"
                        aria-label="Nueva etiqueta"
                        className="h-9 w-32 text-sm"
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddTag() } }}
                      />
                      <Button type="button" variant="outline" size="sm" onClick={handleAddTag} disabled={!newTag.trim() || tags.length >= 10}>
                        Agregar
                      </Button>
                    </div>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--color-ink-muted)' }}>
                    (se guardan con «Guardar cambios»)
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="chat" className="pt-4 animate-fade-in">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium" style={{ color: 'var(--color-ink)' }}>
                      Historial de conversación
                    </div>
                    <span className="text-xs" style={{ color: 'var(--color-ink-muted)' }}>
                      {chat.data?.pages[0]?.total ?? 0} mensajes
                    </span>
                  </div>
                  <div ref={chatRef} className="chat-thread max-h-[500px] overflow-y-auto pr-1">
                    {chat.isLoading ? (
                      <div className="space-y-2"><div className="skel h-12 w-full" /><div className="skel h-12 w-full" /><div className="skel h-12 w-full" /></div>
                    ) : (chat.data?.pages[0]?.total ?? 0) === 0 ? (
                      <div className="empty-state">
                        <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" strokeLinecap="round" strokeLinejoin="round" /></svg>
                        <p className="empty-state-title">Sin mensajes</p>
                        <p className="empty-state-text">Aún no hay conversación registrada con este cliente.</p>
                      </div>
                    ) : (
                      <>
                        {chat.hasPreviousPage && (
                          <div className="flex justify-center pb-1">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => chat.fetchPreviousPage()}
                              disabled={chat.isFetchingPreviousPage}
                              className="w-full sm:w-auto"
                            >
                              {chat.isFetchingPreviousPage ? 'Cargando…' : 'Cargar anteriores'}
                            </Button>
                          </div>
                        )}
                        {[...(chat.data?.pages ?? [])]
                          .flatMap((page) => page.items)
                          .reverse()
                          .map((message: ContactMessage) => (
                            <Tooltip key={message.id} delayDuration={300}>
                              <TooltipTrigger asChild>
                                <div className={cn('chat-bubble', message.direction === 'out' ? 'out' : 'in')}>
                                  <div className="avatar" style={{
                                    background: message.direction === 'out' ? 'var(--color-brand-magenta)' : 'var(--color-raised)',
                                    color: message.direction === 'out' ? 'white' : 'var(--color-ink-soft)',
                                    border: message.direction === 'in' ? '1px solid var(--color-border-subtle)' : 'none',
                                  }}>
                                    {message.direction === 'out' ? 'A' : getInitials(contact.name)}
                                  </div>
                                  <div className={cn('chat-bubble-content', message.direction === 'out' ? 'out' : 'in')}>
                                    <div className="chat-bubble-meta">
                                      <span>{message.direction === 'out' ? 'Aura' : contact.name ?? 'Cliente'}</span>
                                      {typeBadge(message.type) && <span>{typeBadge(message.type)}</span>}
                                      <time>{formatDate(message.created_at)}</time>
                                    </div>
                                    <p className="whitespace-pre-wrap break-words">
                                      {messageBody(message)}
                                    </p>
                                  </div>
                                </div>
                              </TooltipTrigger>
                              <TooltipContent side={message.direction === 'out' ? 'left' : 'right'} align="end">
                                {message.direction === 'out' ? 'Saliente (Aura)' : 'Entrante (Cliente)'}
                                {message.type !== 'text' && <span className="block text-xs mt-1" style={{ color: 'var(--color-ink-muted)' }}>{TYPE_MARKERS[message.type]}</span>}
                              </TooltipContent>
                            </Tooltip>
                          ))}
                      </>
                    )}
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="quotes" className="pt-4 animate-fade-in">
                <div className="space-y-2">
                  {quotesQuery.isLoading ? (
                    <div className="space-y-2"><div className="skel h-12 w-full" /><div className="skel h-12 w-full" /></div>
                  ) : (quotesQuery.data?.length ?? 0) === 0 ? (
                    <div className="empty-state py-8">
                      <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      <p className="empty-state-title">Sin cotizaciones</p>
                      <p className="empty-state-text">Este cliente aún no tiene cotizaciones registradas.</p>
                    </div>
                  ) : (
                    <Table>
                      <TableCaption className="sr-only">Cotizaciones del cliente</TableCaption>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-24">Estado</TableHead>
                          <TableHead>Total</TableHead>
                          <TableHead className="w-40 text-right">Fecha</TableHead>
                          <TableHead className="w-24 text-right">Acción</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {quotesQuery.data?.map((quote: ContactQuote) => (
                          <TableRow key={quote.id} className="hover:bg-muted/50">
                            <TableCell>
                              <Badge variant={statusVariant(quote.status)} className="text-xs capitalize">
                                {quote.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="font-medium tabular" style={{ color: 'var(--color-ink)' }}>
                              ${quote.total.toLocaleString('es-CO')}
                            </TableCell>
                            <TableCell className="text-right text-sm" style={{ color: 'var(--color-ink-soft)' }}>
                              {formatDate(quote.created_at)}
                            </TableCell>
                            <TableCell className="text-right">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="sm" asChild>
                                    <a href={`/cotizador/cotizaciones/${quote.id}`}>
                                      <IconEye className="h-4 w-4" aria-hidden="true" />
                                      <span className="sr-only">Ver cotización</span>
                                    </a>
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent side="left">Ver cotización</TooltipContent>
                              </Tooltip>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </div>
              </TabsContent>

              <TabsContent value="notes" className="pt-4 animate-fade-in">
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Input
                      value={newNote}
                      onChange={(e) => setNewNote(e.target.value)}
                      placeholder="Ej: 14/oct: pidió mantenimiento del tablero"
                      aria-label="Nueva nota del cliente"
                      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddNote() } }}
                      className="flex-1 h-10"
                    />
                    <Button size="sm" onClick={handleAddNote} disabled={createNote.isLoading || !newNote.trim()}>
                      {createNote.isLoading ? 'Guardando…' : 'Agregar nota'}
                    </Button>
                  </div>
                  {notesQuery.error && (
                    <div className="slip" style={{ background: 'var(--color-danger-wash)', borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
                      {notesQuery.error.message}
                    </div>
                  )}
                  {notesQuery.isLoading ? (
                    <div className="space-y-2"><div className="skel h-12 w-full" /><div className="skel h-12 w-full" /></div>
                  ) : (notesQuery.data?.length ?? 0) === 0 ? (
                    <div className="empty-state py-8">
                      <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M11 4a2 2 0 114 0v1a1 1 0 01-1 1H9a1 1 0 11-1-1V4z" strokeLinecap="round" strokeLinejoin="round" /><path d="M18 8a2 2 0 11-4 0h4zM9 20h7a2 2 0 002-2V6a2 2 0 00-2-2H9a2 2 0 00-2 2v12a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      <p className="empty-state-title">Sin notas</p>
                      <p className="empty-state-text">Las que tomes aquí y por chat se verán en la ficha.</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                      {notesQuery.data?.map((note: ContactNote) => (
                        <Card key={note.id} className="ficha animate-slide-in">
                          <CardContent className="pt-3 pb-3">
                            <div className="flex items-baseline justify-between gap-2 mb-1">
                              <time className="text-xs tabular" style={{ color: 'var(--color-ink-muted)' }}>
                                {formatDate(note.created_at)}
                              </time>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button variant="ghost" size="sm" onClick={() => { if (window.confirm('¿Borrar esta nota?')) deleteNote.mutate(note.id) }} disabled={deleteNote.isLoading} aria-label="Borrar nota">
                                    <IconTrash2 className="h-3.5 w-3.5" aria-hidden="true" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent side="top">Borrar nota</TooltipContent>
                              </Tooltip>
                            </div>
                            <p className="whitespace-pre-wrap break-words text-sm" style={{ color: 'var(--color-ink-soft)' }}>
                              {note.content}
                            </p>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </div>
              </TabsContent>
            </Tabs>

            {/* Actions footer */}
            <CardFooter className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t pt-4" style={{ borderColor: 'var(--color-border-subtle)' }}>
              <Button
                variant={contact.is_active ? 'destructive' : 'default'}
                onClick={handleToggleActive}
                disabled={saving || updateContact.isLoading}
                className="w-full sm:w-auto"
              >
                {contact.is_active ? 'Retirar cliente' : 'Reactivar cliente'}
              </Button>
              <div className="flex gap-2 w-full sm:w-auto justify-end">
                <Button variant="outline" onClick={onClose} className="w-full sm:w-auto">Cerrar</Button>
                <Button onClick={handleSave} disabled={saving || updateContact.isLoading} className="w-full sm:w-auto">
                  {saving ? 'Guardando…' : 'Guardar cambios'}
                </Button>
              </div>
              {formError && (
                <div className="w-full">
                  <div className="slip" style={{ background: 'var(--color-danger-wash)', borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
                    {formError}
                  </div>
                </div>
              )}
            </CardFooter>
          </>
        )}
      </Card>
    </TooltipProvider>
  )
}

// ── ClientesPage (List Screen) ──────────────────────────────────────────────

export default function ClientesPage() {
  const { user } = useAuth()
  // La búsqueda global del topbar aterriza aquí: /clientes?search=…
  const [searchParams, setSearchParams] = useSearchParams()
  const urlSearch = searchParams.get('search') ?? ''
  const [search, setSearch] = useState(urlSearch)
  const [debouncedSearch, setDebouncedSearch] = useState(urlSearch)
  const [showRetired, setShowRetired] = useState(false)
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined)
  const [page, setPage] = useState(0)
  const [openId, setOpenId] = useState<string | null>(null)
  const [heldIds, setHeldIds] = useState<Set<string>>(new Set())
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'last_interaction_at', direction: 'desc' })

  // Si el topbar trae una consulta nueva por URL, aplicarla
  useEffect(() => {
    if (urlSearch && urlSearch !== search) {
      setSearch(urlSearch)
      setDebouncedSearch(urlSearch)
      setPage(0)
      // Limpiar el param para no re-aplicarla al volver a la página
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSearch])

  useEffect(() => {
    const timer = setTimeout(() => { setDebouncedSearch(search); setPage(0) }, 300)
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
  const googleContacts = useGoogleContactsStatus()
  const importGoogleContacts = useImportGoogleContacts()

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const hold = (id: string) => setHeldIds((prev) => new Set(prev).add(id))
  const release = (id: string) => setHeldIds((prev) => { const next = new Set(prev); next.delete(id); return next })

  const handleToggleActive = (contact: Contact) => {
    const nextActive = !contact.is_active
    if (!nextActive && !window.confirm(`¿Retirar a ${contact.name ?? contact.wa_id}? Su historial se conserva.`)) return
    updateContact.mutate({ id: contact.id, data: { is_active: nextActive } }, { onSuccess: () => hold(contact.id) })
  }

  const handleSort = (key: string) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
    setPage(0)
  }

  const botName = user?.bot_name ?? 'Aura'

  return (
    <div className="animate-fade-in">
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between gap-4 flex-wrap mb-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--color-ink)' }}>Contactos y clientes</h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              El mini CRM del negocio: quiénes son tus clientes, su historial de conversación, cotizaciones, notas y etiquetas.
            </p>
          </div>
          {user?.is_platform_admin && (
            <span className="rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wider"
              style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}>
              Super Admin
            </span>
          )}
        </div>
      </div>

      <Card className="mb-5 border" style={{ borderColor: 'var(--color-border-default)', background: 'var(--color-raised)' }}>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
          <div className="flex min-w-0 items-start gap-3">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
              style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)' }}
              aria-hidden="true"
            >
              <IconUsers className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                Importar desde Google Contacts
              </p>
              <p className="mt-0.5 text-xs" style={{ color: 'var(--color-ink-muted)' }}>
                Añade contactos con teléfono al CRM sin sobrescribir los datos que ya editaste.
              </p>
              {googleContacts.data?.connected && googleContacts.data.google_email && (
                <p className="mt-1 text-xs" style={{ color: 'var(--color-ink-soft)' }}>
                  Cuenta: {googleContacts.data.google_email}
                </p>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {!googleContacts.data?.connected && !googleContacts.isLoading && (
              <span className="text-xs" style={{ color: 'var(--color-ink-muted)' }}>
                Conéctala en Negocio
              </span>
            )}
            {googleContacts.data?.connected && !googleContacts.data.contacts_permission && (
              <span className="text-xs" style={{ color: 'var(--color-danger)' }}>
                Falta permiso de contactos
              </span>
            )}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={
                !googleContacts.data?.connected ||
                !googleContacts.data.contacts_permission ||
                importGoogleContacts.isLoading
              }
              onClick={() => importGoogleContacts.mutate()}
              aria-label="Importar contactos de Google"
            >
              <IconDownload className="mr-2 h-3.5 w-3.5" aria-hidden="true" />
              {importGoogleContacts.isLoading ? 'Importando…' : 'Importar'}
            </Button>
          </div>
        </CardContent>
        {importGoogleContacts.data && (
          <div className="border-t px-4 py-2 text-xs" style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-ink-soft)' }}>
            Importación terminada: {importGoogleContacts.data.created} nuevos, {importGoogleContacts.data.updated} actualizados y {importGoogleContacts.data.unchanged} sin cambios.
            {importGoogleContacts.data.skipped_no_phone > 0 && ` ${importGoogleContacts.data.skipped_no_phone} sin teléfono fueron omitidos.`}
          </div>
        )}
        {importGoogleContacts.error && (
          <div className="border-t px-4 py-2 text-xs" role="alert" style={{ borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
            {importGoogleContacts.error.message}
          </div>
        )}
      </Card>

      {/* Toolbar: search, filters, tags */}
      <div className="list-toolbar animate-slide-in">
        <div className="list-search relative flex-1 min-w-[200px]">
          <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4" style={{ color: 'var(--color-ink-muted)' }} aria-hidden="true" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nombre o celular…"
            aria-label="Buscar clientes"
            className="h-10 pl-10 pr-4"
            style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border-default)', color: 'var(--color-ink)' }}
          />
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-ink-soft)' }}>
            <Switch
              checked={showRetired}
              onCheckedChange={setShowRetired}
              aria-label="Mostrar clientes retirados"
            />
            Mostrar retirados
          </label>

          {(availableTags?.length ?? 0) > 0 && (
            <div className="relative">
              <Label htmlFor="tag-filter" className="sr-only">Filtrar por etiqueta</Label>
              <Select value={tagFilter ?? ''} onValueChange={(v) => { setTagFilter(v || undefined); setPage(0) }}>
                <SelectTrigger id="tag-filter" className="h-10 w-[180px] min-w-0" style={{ background: 'var(--color-surface)', borderColor: 'var(--color-border-default)', color: 'var(--color-ink)' }}>
                  <SelectValue placeholder="Todas las etiquetas" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Todas</SelectItem>
                  <SelectItem value="" disabled className="text-xs text-muted-foreground">— Etiquetas —</SelectItem>
                  {availableTags?.map((tag: string) => (
                    <SelectItem key={tag} value={tag}>{tag}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="list-count hidden sm:block" style={{ color: 'var(--color-ink-muted)' }}>
            {data ? `Mostrando ${data.items.length} de ${data.total}` : 'Cargando…'}
          </div>
        </div>
      </div>

      {/* Errors */}
      <div className="mb-4" role="alert">
        {error && (
          <div className="slip" style={{ background: 'var(--color-danger-wash)', borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
            {error.message}
          </div>
        )}
        {updateContact.error && (
          <div className="slip" style={{ background: 'var(--color-danger-wash)', borderColor: 'var(--color-danger-border)', color: 'var(--color-danger)' }}>
            {updateContact.error.message}
          </div>
        )}
      </div>

      {/* Table (List Screen) */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="col-identity">Nombre</TableHead>
                  <TableHead>Celular</TableHead>
                  <TableHead>Última interacción</TableHead>
                  <TableHead className="col-number">Mensajes</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="col-actions">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...Array(6)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell className="col-identity"><div className="skel h-4 w-1/3" /></TableCell>
                    <TableCell><div className="skel h-4 w-24" /></TableCell>
                    <TableCell><div className="skel h-4 w-28" /></TableCell>
                    <TableCell className="col-number"><div className="skel h-4 w-12" /></TableCell>
                    <TableCell><div className="skel h-5 w-20" /></TableCell>
                    <TableCell className="col-actions"><div className="skel h-8 w-32" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="col-identity">
                    <Button variant="ghost" size="sm" onClick={() => handleSort('name')} className="flex items-center gap-1 h-auto p-0 text-left font-semibold">
                      Nombre {sortConfig.key === 'name' && (sortConfig.direction === 'asc' ? <IconChevronUp className="h-3.5 w-3.5" /> : <IconChevronDown className="h-3.5 w-3.5" />)}
                    </Button>
                  </TableHead>
                  <TableHead>
                    <Button variant="ghost" size="sm" onClick={() => handleSort('wa_id')} className="flex items-center gap-1 h-auto p-0">
                      Celular {sortConfig.key === 'wa_id' && (sortConfig.direction === 'asc' ? <IconChevronUp className="h-3.5 w-3.5" /> : <IconChevronDown className="h-3.5 w-3.5" />)}
                    </Button>
                  </TableHead>
                  <TableHead>
                    <Button variant="ghost" size="sm" onClick={() => handleSort('last_interaction_at')} className="flex items-center gap-1 h-auto p-0">
                      Última interacción {sortConfig.key === 'last_interaction_at' && (sortConfig.direction === 'asc' ? <IconChevronUp className="h-3.5 w-3.5" /> : <IconChevronDown className="h-3.5 w-3.5" />)}
                    </Button>
                  </TableHead>
                  <TableHead className="col-number">
                    <Button variant="ghost" size="sm" onClick={() => handleSort('messages_count')} className="flex items-center gap-1 h-auto p-0 justify-end">
                      Mensajes {sortConfig.key === 'messages_count' && (sortConfig.direction === 'asc' ? <IconChevronUp className="h-3.5 w-3.5" /> : <IconChevronDown className="h-3.5 w-3.5" />)}
                    </Button>
                  </TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="col-actions">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((contact: Contact) => (
                  <TableRow
                    key={contact.id}
                    className={cn(
                      'border-b transition-colors last:border-0 hover:bg-muted/50',
                      heldIds.has(contact.id) && 'row-hold'
                    )}
                    onMouseEnter={() => release(contact.id)}
                    onFocus={() => release(contact.id)}
                  >
                    <TableCell className="col-identity">
                      <div className="flex items-center gap-2.5">
                        <Avatar className="h-7 w-7">
                          <AvatarImage src="" alt="" />
                          <AvatarFallback className="text-xs font-medium" style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)' }}>
                            {getInitials(contact.name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <div className="font-medium truncate" style={{ color: 'var(--color-ink)' }}>
                            {contact.name ?? 'Sin nombre'}
                          </div>
                          {(contact.tags?.length ?? 0) > 0 && (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {contact.tags.slice(0, 3).map((tag: string) => (
                                <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0.5">
                                  {tag}
                                </Badge>
                              ))}
                              {contact.tags.length > 3 && (
                                <Badge variant="outline" className="text-[10px]">+{contact.tags.length - 3}</Badge>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="tabular" style={{ color: 'var(--color-ink-soft)' }}>
                      {contact.wa_id}
                    </TableCell>
                    <TableCell className="tabular text-sm" style={{ color: 'var(--color-ink-soft)' }}>
                      {formatDate(contact.last_interaction_at)}
                    </TableCell>
                    <TableCell className="col-number tabular font-medium" style={{ color: 'var(--color-ink)' }}>
                      {contact.messages_count}
                    </TableCell>
                    <TableCell>
                      <Badge variant={contact.is_active ? 'default' : 'secondary'} className="text-xs capitalize">
                        {contact.is_active ? 'Activo' : 'Retirado'}
                      </Badge>
                    </TableCell>
                    <TableCell className="col-actions">
                      <div className="flex items-center justify-end gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button variant="ghost" size="sm" onClick={() => setOpenId(contact.id)} aria-label={`Abrir ficha de ${contact.name ?? contact.wa_id}`}>
                              <IconEye className="h-3.5 w-3.5" aria-hidden="true" />
                              <span className="hidden sm:inline">Abrir</span>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="left">Abrir ficha</TooltipContent>
                        </Tooltip>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant={contact.is_active ? 'destructive' : 'default'}
                              size="sm"
                              onClick={() => handleToggleActive(contact)}
                              disabled={updateContact.isLoading}
                              aria-label={contact.is_active ? `Retirar a ${contact.name ?? contact.wa_id}` : `Reactivar a ${contact.name ?? contact.wa_id}`}
                            >
                              {contact.is_active ? <IconPerson className="h-3.5 w-3.5" /> : <IconPerson className="h-3.5 w-3.5" />}
                              <span className="hidden sm:inline">{contact.is_active ? 'Retirar' : 'Reactivar'}</span>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent side="left">{contact.is_active ? 'Retirar cliente' : 'Reactivar cliente'}</TooltipContent>
                        </Tooltip>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : debouncedSearch.trim().length > 0 ? (
          <div className="empty-state py-12">
            <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <p className="empty-state-title">Ningún cliente coincide</p>
            <p className="empty-state-text">Pruebe con otro nombre o celular, o limpie la búsqueda para verlos todos.</p>
            <div className="mt-4">
              <Button variant="outline" onClick={() => setSearch('')}>Limpiar búsqueda</Button>
            </div>
          </div>
        ) : (
          <div className="empty-state py-16">
            <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7.108 2.254A12.061 12.061 0 0112 1.5c2.287 0 4.424.605 6.196 1.736" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <p className="empty-state-title">Todavía no hay clientes</p>
            <p className="empty-state-text">Cuando alguien escriba al WhatsApp del asistente, su ficha aparecerá aquí automáticamente con su primera conversación.</p>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.items.length > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm" style={{ color: 'var(--color-ink-muted)' }}>
          <span className="tabular">Página {page + 1} de {totalPages} · {data.total} clientes</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>Anterior</Button>
            <Button variant="outline" size="sm" onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))} disabled={page + 1 >= totalPages}>Siguiente</Button>
          </div>
        </div>
      )}

      {/* ContactFicha Modal */}
      {openId && (
        <ContactFicha contactId={openId} onClose={() => setOpenId(null)} />
      )}
    </div>
  )
}