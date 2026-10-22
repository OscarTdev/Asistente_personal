// Quote detail: the slip ready to hand over — status, notes, editable
// items with hold-on-change, and the PDF download.

import { FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Card from '../components/ui/card'
import Input from '../components/ui/input'
import Modal from '../components/ui/modal'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'
import { IconArrowLeft, IconDownload, IconPlus } from '../components/ui/icons'
import { downloadQuotePdf } from '../lib/api'
import { formatCOP, formatDate, round2 } from '../lib/format'
import { QUOTE_STATUSES, QUOTE_STATUS_LABELS, QuoteStatusBadge } from '../lib/quoteStatus'
import {
  useAddQuoteItem,
  useDeleteQuoteItem,
  useQuote,
  useUpdateQuote,
  useUpdateQuoteItem,
} from '../hooks/useQuotes'
import { QuoteItem } from '../types'

const numberInputClasses =
  'flex h-11 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm tabular text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep'

// ── Item modal (add / edit) ──────────────────────────────────────────────────

function QuoteItemModal({
  open,
  item,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean
  item: QuoteItem | null
  saving: boolean
  error: string | null
  onClose: () => void
  onSubmit: (data: { description: string; quantity: number; unitPrice: number }) => void
}) {
  const [description, setDescription] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unitPrice, setUnitPrice] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setDescription(item?.description ?? '')
      setQuantity(item ? String(item.quantity) : '1')
      setUnitPrice(item ? String(item.unit_price) : '')
      setFormError(null)
    }
  }, [open, item])

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const qty = parseFloat(quantity)
    const price = parseFloat(unitPrice)
    if (!description.trim() || Number.isNaN(qty) || qty <= 0 || Number.isNaN(price) || price < 0) {
      setFormError('La descripción es obligatoria; la cantidad debe ser mayor que 0 y el precio válido.')
      return
    }
    onSubmit({ description: description.trim(), quantity: round2(qty), unitPrice: round2(price) })
  }

  return (
    <Modal open={open} title={item ? 'Editar ítem' : 'Agregar ítem'} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="item-description">
            Descripción
          </label>
          <Input
            id="item-description"
            value={description}
            onChangeValue={setDescription}
            placeholder="Ej: Cable THHN #12, 30 metros"
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="item-quantity">
              Cantidad
            </label>
            <input
              id="item-quantity"
              type="number"
              step="0.01"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className={numberInputClasses}
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="item-price">
              Precio unitario (COP)
            </label>
            <input
              id="item-price"
              type="number"
              step="0.01"
              min="0"
              value={unitPrice}
              onChange={(e) => setUnitPrice(e.target.value)}
              className={numberInputClasses}
              placeholder="0.00"
              required
            />
          </div>
        </div>
        {formError && <p className="text-sm text-lacre">{formError}</p>}
        {error && <ErrorSlip message={error} />}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QuoteDetailPage() {
  const { id } = useParams()
  const quoteId = id ?? ''
  const { data: quote, isLoading, error } = useQuote(quoteId)
  const updateQuote = useUpdateQuote(quoteId)
  const addItem = useAddQuoteItem(quoteId)
  const updateItem = useUpdateQuoteItem(quoteId)
  const deleteItem = useDeleteQuoteItem(quoteId)

  const [notes, setNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)
  const [addingItem, setAddingItem] = useState(false)
  const [editingItem, setEditingItem] = useState<QuoteItem | null>(null)
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [heldIds, setHeldIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (quote) {
      setNotes(quote.notes ?? '')
    }
  }, [quote])

  const hold = (itemId: string) => {
    setHeldIds((previous) => new Set(previous).add(itemId))
  }
  const release = (itemId: string) => {
    setHeldIds((previous) => {
      const next = new Set(previous)
      next.delete(itemId)
      return next
    })
  }

  const handleSaveNotes = () => {
    setSavingNotes(true)
    updateQuote.mutate(
      { notes: notes.trim() || null },
      {
        onSettled: () => setSavingNotes(false),
      }
    )
  }

  const handleStatusChange = (status: string) => {
    updateQuote.mutate({ status })
  }

  const handleDownloadPdf = async () => {
    if (!quote) {
      return
    }
    setDownloadingPdf(true)
    setPdfError(null)
    try {
      await downloadQuotePdf(quote.id)
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : 'Error al generar el PDF')
    } finally {
      setDownloadingPdf(false)
    }
  }

  if (isLoading) {
    return (
      <div className="ficha max-w-3xl p-6">
        <div className="skel h-6 w-1/3" />
        <div className="skel mt-4 h-4 w-1/2" />
        <div className="skel mt-8 h-32 w-full" />
      </div>
    )
  }
  if (error) {
    return <ErrorSlip message={error.message} />
  }
  if (!quote) {
    return null
  }

  const items = quote.items ?? []

  return (
    <div>
      {/* Back to the desk */}
      <Link
        to="/cotizador/cotizaciones"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-pine hover:underline"
      >
        <IconArrowLeft className="h-4 w-4" />
        Cotizaciones
      </Link>

      {/* Slip header */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="tabular text-2xl font-semibold tracking-tight text-ink">
            Cotización #{quote.id.slice(0, 8)}
          </h1>
          <QuoteStatusBadge status={quote.status} />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={quote.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            disabled={updateQuote.isLoading}
            className="h-10 rounded-md border border-linen-300 bg-panel px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep disabled:opacity-50"
            aria-label="Cambiar estado"
          >
            {QUOTE_STATUSES.map((status) => (
              <option key={status} value={status}>
                {QUOTE_STATUS_LABELS[status]}
              </option>
            ))}
          </select>
          <Button
            type="button"
            onClick={handleDownloadPdf}
            disabled={downloadingPdf || items.length === 0}
          >
            <IconDownload className="h-4 w-4" />
            {downloadingPdf ? 'Generando…' : 'Descargar PDF'}
          </Button>
        </div>
      </div>
      <div className="mt-3 space-y-3">
        <ErrorSlip message={pdfError} onDismiss={() => setPdfError(null)} />
      </div>

      {/* Summary */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="p-4">
          <div className="plate-label">Preparada</div>
          <div className="tabular mt-1 text-sm font-medium text-ink">{formatDate(quote.created_at)}</div>
        </Card>
        <Card className="p-4">
          <div className="plate-label">Actualizada</div>
          <div className="tabular mt-1 text-sm font-medium text-ink">{formatDate(quote.updated_at)}</div>
        </Card>
        <Card className="p-4">
          <div className="plate-label">Válida hasta</div>
          <div className="tabular mt-1 text-sm font-medium text-ink">{formatDate(quote.valid_until)}</div>
        </Card>
        <Card className="border-pine/30 bg-pine-wash p-4">
          <div className="plate-label text-ink-soft/80">Total</div>
          <div className="tabular mt-1 text-lg font-bold text-pine">{formatCOP(quote.total)}</div>
        </Card>
      </div>

      {/* Notes */}
      <Card className="mt-6 p-5">
        <h2 className="text-sm font-semibold text-ink">Notas</h2>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder="Condiciones, alcance, observaciones…"
          className="mt-2 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm text-ink placeholder:text-linen-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep"
        />
        <div className="mt-2 flex justify-end">
          <Button type="button" variant="outline" size="sm" onClick={handleSaveNotes} disabled={savingNotes}>
            {savingNotes ? 'Guardando…' : 'Guardar notas'}
          </Button>
        </div>
      </Card>

      {/* Items */}
      <Card className="mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-linen-100 px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">
            Ítems {items.length > 0 && <span className="tabular text-linen-600">({items.length})</span>}
          </h2>
          <Button type="button" variant="outline" size="sm" onClick={() => setAddingItem(true)}>
            <IconPlus className="h-4 w-4" />
            Agregar ítem
          </Button>
        </div>
        {items.length === 0 ? (
          <div className="px-6 py-8 text-center">
            <p className="text-sm font-medium text-ink">Esta cotización no tiene ítems todavía</p>
            <p className="mt-1 text-xs text-linen-600">
              Agregue el primero y el asistente recalculará el total.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  <th className="plate-label px-4 py-3 font-semibold">Descripción</th>
                  <th className="plate-label px-4 py-3 font-semibold">Cant.</th>
                  <th className="plate-label px-4 py-3 font-semibold">Precio unit.</th>
                  <th className="plate-label px-4 py-3 font-semibold">Total</th>
                  <th className="plate-label px-4 py-3 text-right font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={`border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50 ${
                      heldIds.has(item.id) ? 'row-hold' : ''
                    }`}
                    onMouseEnter={() => release(item.id)}
                    onFocus={() => release(item.id)}
                  >
                    <td className="px-4 py-3 font-medium text-ink">{item.description}</td>
                    <td className="tabular px-4 py-3 text-ink-soft">{item.quantity}</td>
                    <td className="tabular px-4 py-3 text-ink-soft">{formatCOP(item.unit_price)}</td>
                    <td className="tabular px-4 py-3 font-semibold text-ink">
                      {formatCOP(item.line_total)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setEditingItem(item)}
                        className="rounded px-2 py-1.5 text-sm font-medium text-pine hover:bg-pine-wash"
                      >
                        Editar
                      </button>
                      {/* Destructive action kept apart, outline style */}
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`¿Eliminar "${item.description}" de la cotización?`)) {
                            deleteItem.mutate(item.id)
                          }
                        }}
                        disabled={deleteItem.isLoading}
                        className="ml-3 rounded border border-lacre/40 px-2.5 py-1.5 text-sm font-medium text-lacre hover:bg-lacre-wash disabled:opacity-50"
                      >
                        Eliminar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Add item modal */}
      <QuoteItemModal
        open={addingItem}
        item={null}
        saving={addItem.isLoading}
        error={addItem.error?.message ?? null}
        onClose={() => setAddingItem(false)}
        onSubmit={({ description, quantity, unitPrice }) => {
          addItem.mutate(
            { description, quantity, unit_price: unitPrice },
            {
              onSuccess: (created) => {
                setAddingItem(false)
                hold(created.id)
              },
            }
          )
        }}
      />

      {/* Edit item modal */}
      <QuoteItemModal
        open={editingItem !== null}
        item={editingItem}
        saving={updateItem.isLoading}
        error={updateItem.error?.message ?? null}
        onClose={() => setEditingItem(null)}
        onSubmit={({ description, quantity, unitPrice }) => {
          if (!editingItem) {
            return
          }
          updateItem.mutate(
            { itemId: editingItem.id, data: { description, quantity, unit_price: unitPrice } },
            {
              onSuccess: (updated) => {
                setEditingItem(null)
                hold(updated.id)
              },
            }
          )
        }}
      />
    </div>
  )
}
