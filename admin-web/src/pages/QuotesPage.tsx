// Quotes desk: the list as the day's ledger, the new-quote modal as the
// concierge taking dictation (AI extraction + manual items).

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/card'
import Input from '../components/ui/input'
import Modal from '../components/ui/modal'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'
import { IconPlus, IconX } from '../components/ui/icons'
import { useCreateQuote, useExtractItems, useQuotes } from '../hooks/useQuotes'
import { formatCOP, formatDate, round2 } from '../lib/format'
import { QUOTE_STATUSES, QUOTE_STATUS_LABELS, QuoteStatusBadge } from '../lib/quoteStatus'
import { QuoteCreatePayload } from '../types'

const PAGE_SIZE = 10

const numberInputClasses =
  'flex h-11 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm tabular text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep'

// ── Draft items ──────────────────────────────────────────────────────────────

interface DraftItem {
  description: string
  quantity: string
  unitPrice: string
  catalogItemId: string | null
  catalogName: string | null
  matched: boolean
}

// ── New quote modal ──────────────────────────────────────────────────────────

function NewQuoteModal({
  open,
  saving,
  createError,
  onClose,
  onSubmit,
}: {
  open: boolean
  saving: boolean
  createError: string | null
  onClose: () => void
  onSubmit: (payload: QuoteCreatePayload) => void
}) {
  const extract = useExtractItems()
  const [text, setText] = useState('')
  const [items, setItems] = useState<DraftItem[]>([])
  const [notes, setNotes] = useState('')
  const [validUntil, setValidUntil] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [manual, setManual] = useState({ description: '', quantity: '1', unitPrice: '' })

  // Reset the dictation pad every time the modal opens
  useEffect(() => {
    if (open) {
      setText('')
      setItems([])
      setNotes('')
      setValidUntil('')
      setFormError(null)
      setManual({ description: '', quantity: '1', unitPrice: '' })
      extract.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleExtract = () => {
    const trimmed = text.trim()
    if (!trimmed) {
      return
    }
    extract.mutate(trimmed, {
      onSuccess: (response) => {
        setItems((previous) => [
          ...previous,
          ...response.suggestions.map((suggestion) => ({
            description: suggestion.description,
            quantity: String(suggestion.quantity ?? 1),
            unitPrice: suggestion.unit_price != null ? String(suggestion.unit_price) : '',
            catalogItemId: suggestion.catalog_item_id,
            catalogName: suggestion.catalog_name,
            matched: suggestion.matched,
          })),
        ])
      },
    })
  }

  const addManualItem = () => {
    if (!manual.description.trim()) {
      return
    }
    setItems((previous) => [
      ...previous,
      {
        description: manual.description.trim(),
        quantity: manual.quantity || '1',
        unitPrice: manual.unitPrice,
        catalogItemId: null,
        catalogName: null,
        matched: false,
      },
    ])
    setManual({ description: '', quantity: '1', unitPrice: '' })
  }

  const updateItem = (index: number, patch: Partial<DraftItem>) => {
    setItems((previous) => previous.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  const removeItem = (index: number) => {
    setItems((previous) => previous.filter((_, i) => i !== index))
  }

  const handleSubmit = () => {
    const payloadItems: QuoteCreatePayload['items'] = []
    for (const item of items) {
      const quantity = parseFloat(item.quantity)
      const unitPrice = parseFloat(item.unitPrice)
      if (
        !item.description.trim() ||
        Number.isNaN(quantity) ||
        quantity <= 0 ||
        Number.isNaN(unitPrice) ||
        unitPrice < 0
      ) {
        setFormError('Revise los ítems: cada uno necesita descripción, cantidad mayor que 0 y un precio válido.')
        return
      }
      payloadItems.push({
        description: item.description.trim(),
        quantity: round2(quantity),
        unit_price: round2(unitPrice),
        catalog_item_id: item.catalogItemId,
      })
    }
    setFormError(null)
    onSubmit({
      notes: notes.trim() || null,
      valid_until: validUntil ? new Date(`${validUntil}T12:00:00`).toISOString() : null,
      items: payloadItems,
    })
  }

  return (
    <Modal open={open} title="Nueva cotización" onClose={onClose} wide>
      <div className="space-y-6">
        {/* AI dictation */}
        <section>
          <h3 className="text-sm font-semibold text-ink">Tomar dictado con IA</h3>
          <p className="mt-1 text-xs text-linen-600">
            Pegue el mensaje del técnico (texto o audio transcrito). El asistente extrae los
            materiales y los busca en el catálogo. Los precios salen del libro: la IA nunca inventa
            precios.
          </p>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={5000}
            placeholder="Ej: necesito 10 tomacorrientes dobles, 30 metros de cable THHN #12 y 2 horas de mano de obra"
            className="mt-2 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm text-ink placeholder:text-linen-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep"
          />
          <div className="mt-2 flex items-center gap-3">
            <Button
              type="button"
              onClick={handleExtract}
              disabled={extract.isLoading || !text.trim()}
            >
              {extract.isLoading ? 'Transcribiendo…' : 'Extraer con IA'}
            </Button>
            {extract.error && <p className="text-sm text-lacre">{extract.error.message}</p>}
          </div>
        </section>

        {/* Draft items */}
        <section>
          <h3 className="text-sm font-semibold text-ink">
            Ítems {items.length > 0 && <span className="tabular text-linen-600">({items.length})</span>}
          </h3>
          {items.length === 0 ? (
            <p className="mt-2 text-xs text-linen-600">
              Todavía no hay ítems. Use el dictado con IA o agregue uno a mano.
            </p>
          ) : (
            <div className="mt-2 space-y-2">
              {items.map((item, index) => (
                <div key={index} className="flex flex-wrap items-center gap-2 rounded-md border border-linen-200 bg-linen-50 p-2">
                  <div className="min-w-[180px] flex-1">
                    <Input
                      value={item.description}
                      onChangeValue={(value) => updateItem(index, { description: value })}
                      placeholder="Descripción"
                      aria-label={`Descripción del ítem ${index + 1}`}
                    />
                  </div>
                  {item.matched && (
                    <span className="rounded-full bg-ok-wash px-2 py-1 text-xs font-medium text-ok">
                      del catálogo{item.catalogName ? `: ${item.catalogName}` : ''}
                    </span>
                  )}
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={item.quantity}
                    onChange={(e) => updateItem(index, { quantity: e.target.value })}
                    className={`${numberInputClasses} w-24`}
                    aria-label={`Cantidad del ítem ${index + 1}`}
                  />
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={item.unitPrice}
                    onChange={(e) => updateItem(index, { unitPrice: e.target.value })}
                    className={`${numberInputClasses} w-32`}
                    aria-label={`Precio unitario del ítem ${index + 1}`}
                    placeholder="Precio"
                  />
                  <button
                    type="button"
                    onClick={() => removeItem(index)}
                    className="rounded p-2 text-linen-500 hover:bg-lacre-wash hover:text-lacre"
                    aria-label={`Quitar ítem ${index + 1}`}
                  >
                    <IconX className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Manual add */}
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-dashed border-linen-300 p-2">
            <div className="min-w-[180px] flex-1">
              <Input
                value={manual.description}
                onChangeValue={(value) => setManual({ ...manual, description: value })}
                placeholder="Ítem manual: descripción"
                aria-label="Descripción del ítem manual"
              />
            </div>
            <input
              type="number"
              step="0.01"
              min="0"
              value={manual.quantity}
              onChange={(e) => setManual({ ...manual, quantity: e.target.value })}
              className={`${numberInputClasses} w-24`}
              aria-label="Cantidad manual"
              placeholder="Cant."
            />
            <input
              type="number"
              step="0.01"
              min="0"
              value={manual.unitPrice}
              onChange={(e) => setManual({ ...manual, unitPrice: e.target.value })}
              className={`${numberInputClasses} w-32`}
              aria-label="Precio unitario manual"
              placeholder="Precio"
            />
            <Button
              type="button"
              variant="outline"
              onClick={addManualItem}
              disabled={!manual.description.trim()}
            >
              Agregar
            </Button>
          </div>
        </section>

        {/* General data */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="quote-notes">
              Notas
            </label>
            <textarea
              id="quote-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Opcional: condiciones, alcance, observaciones…"
              className="w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm text-ink placeholder:text-linen-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="quote-valid-until">
              Válida hasta
            </label>
            <input
              id="quote-valid-until"
              type="date"
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
              className={numberInputClasses}
            />
          </div>
        </section>

        {formError && <p className="text-sm text-lacre">{formError}</p>}
        {createError && <ErrorSlip message={createError} />}

        <div className="flex justify-end gap-2 border-t border-linen-100 pt-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={saving || items.length === 0}>
            {saving ? 'Preparando…' : 'Preparar cotización'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function QuotesPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)
  const [creating, setCreating] = useState(false)

  const { data, isLoading, error } = useQuotes({
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    status: statusFilter,
  })
  const createQuote = useCreateQuote()

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const handleCreate = (payload: QuoteCreatePayload) => {
    createQuote.mutate(payload, {
      onSuccess: (quote) => {
        setCreating(false)
        navigate(`/servicios/quoter/cotizaciones/${quote.id}`)
      },
    })
  }

  return (
    <div>
      {/* Desk header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Cotizaciones</h1>
          <p className="mt-1 text-sm text-linen-600">
            Listas para entregar: genérelas desde el catálogo o desde el dictado con IA.
          </p>
        </div>
        <Button type="button" onClick={() => setCreating(true)}>
          <IconPlus className="h-4 w-4" />
          Nueva cotización
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium text-ink-soft" htmlFor="quote-status-filter">
          Estado
        </label>
        <select
          id="quote-status-filter"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(0)
          }}
          className="h-11 rounded-md border border-linen-300 bg-panel px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep"
        >
          <option value="">Todas</option>
          {QUOTE_STATUSES.map((status) => (
            <option key={status} value={status}>
              {QUOTE_STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      {/* Errors as persistent errata slips */}
      <div className="mb-4 space-y-3">
        <ErrorSlip message={error?.message ?? createQuote.error?.message ?? null} />
      </div>

      {/* The day's ledger */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-linen-100">
            {[0, 1, 2, 3, 4, 5].map((index) => (
              <div key={index} className="flex h-12 items-center gap-4 px-4">
                <div className="skel h-4 w-20" />
                <div className="skel h-4 w-24" />
                <div className="skel ml-auto h-4 w-28" />
              </div>
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  <th className="plate-label px-4 py-3 font-semibold">Fecha</th>
                  <th className="plate-label px-4 py-3 font-semibold">Estado</th>
                  <th className="plate-label px-4 py-3 font-semibold">Total</th>
                  <th className="plate-label px-4 py-3 font-semibold">Notas</th>
                  <th className="plate-label px-4 py-3 text-right font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((quote) => (
                  <tr
                    key={quote.id}
                    className="border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50"
                  >
                    <td className="tabular px-4 py-3 text-ink-soft">{formatDate(quote.created_at)}</td>
                    <td className="px-4 py-3">
                      <QuoteStatusBadge status={quote.status} />
                    </td>
                    <td className="tabular px-4 py-3 font-semibold text-ink">
                      {formatCOP(quote.total)}
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-ink-soft">
                      {quote.notes ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => navigate(`/servicios/quoter/cotizaciones/${quote.id}`)}
                        className="rounded px-2 py-1.5 text-sm font-medium text-pine hover:bg-pine-wash"
                      >
                        Abrir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-10 text-center">
            {statusFilter ? (
              <>
                <p className="text-sm font-medium text-ink">
                  Ninguna cotización con estado «{QUOTE_STATUS_LABELS[statusFilter]}»
                </p>
                <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
                  Cambie el filtro para ver las demás cotizaciones del mostrador.
                </p>
                <div className="mt-4 flex justify-center">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setStatusFilter('')
                      setPage(0)
                    }}
                  >
                    Ver todas
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-ink">Aún no hay cotizaciones</p>
                <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
                  Pegue el mensaje del técnico y use «Extraer con IA», o arme la primera cotización a
                  mano. El asistente la deja lista para entregar en PDF.
                </p>
                <div className="mt-4 flex justify-center">
                  <Button type="button" onClick={() => setCreating(true)}>
                    <IconPlus className="h-4 w-4" />
                    Nueva cotización
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.items.length > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm text-linen-600">
          <span className="tabular">
            Página {page + 1} de {totalPages} · {data.total} cotizaciones
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

      {/* New quote modal */}
      <NewQuoteModal
        open={creating}
        saving={createQuote.isLoading}
        createError={createQuote.error?.message ?? null}
        onClose={() => setCreating(false)}
        onSubmit={handleCreate}
      />
    </div>
  )
}
