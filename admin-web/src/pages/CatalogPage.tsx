// The price book: every COP figure in tabular type, rows hanging from a
// pine desk edge, changes held until seen, destructive actions isolated.

import { FormEvent, useEffect, useRef, useState } from 'react'
import { Card } from "../components/ui/card"
import { Input } from "../components/ui/input"
import { Modal } from "../components/ui/modal"
import { Switch } from "../components/ui/switch"
import { Button } from "../components/ui/button"
import { ErrorSlip } from "../components/ui/error-slip"
import { IconPlus, IconUpload } from "@/components/ui/icons"
import {
  useCatalog,
  useCreateCatalogItem,
  useDeleteCatalogItem,
  useImportCatalogCsv,
  useUpdateCatalogItem,
} from '../hooks/useCatalog'
import { formatCOP, round2 } from '../lib/format'
import { CatalogImportResult, CatalogItem, CatalogItemPayload } from '../types'

const PAGE_SIZE = 10

const numberInputClasses =
  'flex h-11 w-full rounded-md border border-linen-300 bg-panel px-3 py-2 text-sm tabular text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass-deep'

// ── Item modal ────────────────────────────────────────────────────────────────

interface CatalogForm {
  name: string
  description: string
  unit: string
  price: string
}

const emptyForm: CatalogForm = { name: '', description: '', unit: '', price: '' }

function CatalogItemModal({
  open,
  item,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  open: boolean
  item: CatalogItem | null
  saving: boolean
  error: string | null
  onClose: () => void
  onSubmit: (form: CatalogForm) => void
}) {
  const [form, setForm] = useState<CatalogForm>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setForm(
        item
          ? {
              name: item.name,
              description: item.description ?? '',
              unit: item.unit ?? '',
              price: String(item.unit_price),
            }
          : emptyForm
      )
      setFormError(null)
    }
  }, [open, item])

  const price = parseFloat(form.price)
  const isValid =
    form.name.trim().length > 0 &&
    form.price.trim().length > 0 &&
    !Number.isNaN(price) &&
    price >= 0

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!isValid) {
      setFormError('El nombre es obligatorio y el precio debe ser un número válido (≥ 0).')
      return
    }
    onSubmit(form)
  }

  return (
    <Modal open={open} title={item ? 'Editar ítem' : 'Nuevo ítem del catálogo'} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="catalog-name">
            Nombre
          </label>
          <Input
            id="catalog-name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Ej: Tomacorriente doble"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="catalog-description">
            Descripción
          </label>
          <Input
            id="catalog-description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Opcional"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="catalog-unit">
              Unidad
            </label>
            <Input
              id="catalog-unit"
              value={form.unit}
              onChange={(e) => setForm({ ...form, unit: e.target.value })}
              placeholder="unidad, metro, hora…"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-ink-soft" htmlFor="catalog-price">
              Precio unitario (COP)
            </label>
            <input
              id="catalog-price"
              type="number"
              step="0.01"
              min="0"
              value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })}
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
            {saving ? 'Guardando…' : 'Guardar en el libro'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CatalogPage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [page, setPage] = useState(0)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<CatalogItem | null>(null)
  const [importResult, setImportResult] = useState<CatalogImportResult | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [heldIds, setHeldIds] = useState<Set<string>>(new Set())
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Debounce the search so the book stays quiet under fast typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setPage(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const { data, isLoading, error } = useCatalog({
    skip: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    search: debouncedSearch,
    activeOnly: !showInactive,
  })
  const createItem = useCreateCatalogItem()
  const updateItem = useUpdateCatalogItem()
  const deleteItem = useDeleteCatalogItem()
  const importCsv = useImportCatalogCsv()

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

  const handleSubmit = (form: CatalogForm) => {
    const payload: CatalogItemPayload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
      unit: form.unit.trim() || null,
      unit_price: round2(parseFloat(form.price)),
    }
    const onSuccess = (item: CatalogItem) => {
      setCreating(false)
      setEditing(null)
      setActionError(null)
      hold(item.id)
    }
    const onError = (err: Error) => setActionError(err.message)

    if (editing) {
      updateItem.mutate({ id: editing.id, data: payload }, { onSuccess, onError })
    } else {
      createItem.mutate(payload, { onSuccess, onError })
    }
  }

  const handleDelete = (item: CatalogItem) => {
    if (!window.confirm(`¿Retirar "${item.name}" del catálogo?`)) {
      return
    }
    setActionError(null)
    deleteItem.mutate(item.id, {
      onError: (err: Error) => setActionError(err.message),
    })
  }

  const handleImportFile = (file: File | undefined) => {
    if (!file) {
      return
    }
    setActionError(null)
    importCsv.mutate(file, {
      onSuccess: setImportResult,
      onError: (err: Error) => setActionError(err.message),
    })
  }

  return (
    <div>
      {/* Desk header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Catálogo de precios</h1>
          <p className="mt-1 text-sm text-linen-600">
            El libro del asistente: los precios de las cotizaciones salen siempre de aquí.
          </p>
        </div>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              handleImportFile(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          <Button
            type="button"
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={importCsv.isLoading}
          >
            <IconUpload className="h-4 w-4" />
            {importCsv.isLoading ? 'Importando…' : 'Importar CSV'}
          </Button>
          <Button type="button" onClick={() => setCreating(true)}>
            <IconPlus className="h-4 w-4" />
            Agregar ítem
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="w-full max-w-xs">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nombre…"
            aria-label="Buscar en el catálogo"
          />
        </div>
        <label className="flex items-center gap-2.5 text-sm text-ink-soft">
          <Switch checked={showInactive} onCheckedChange={(checked) => setShowInactive(checked)} />
          Mostrar inactivos
        </label>
      </div>

      {/* Errors as persistent errata slips */}
      <div className="mb-4 space-y-3">
        <ErrorSlip message={error?.message ?? actionError} />
      </div>

      {/* The book */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="divide-y divide-linen-100">
            {[0, 1, 2, 3, 4, 5].map((index: number) => (
              <div key={index} className="flex h-12 items-center gap-4 px-4">
                <div className="skel h-4 w-1/3" />
                <div className="skel ml-auto h-4 w-20" />
                <div className="skel h-4 w-14" />
              </div>
            ))}
          </div>
        ) : data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  <th className="plate-label px-4 py-3 font-semibold">Nombre</th>
                  <th className="plate-label px-4 py-3 font-semibold">Descripción</th>
                  <th className="plate-label px-4 py-3 font-semibold">Unidad</th>
                  <th className="plate-label px-4 py-3 font-semibold">Precio</th>
                  <th className="plate-label px-4 py-3 font-semibold">Estado</th>
                  <th className="plate-label px-4 py-3 text-right font-semibold">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item: CatalogItem) => (
                  <tr
                    key={item.id}
                    className={`border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50 ${
                      heldIds.has(item.id) ? 'row-hold' : ''
                    }`}
                    onMouseEnter={() => release(item.id)}
                    onFocus={() => release(item.id)}
                  >
                    <td className="px-4 py-3 font-medium text-ink">{item.name}</td>
                    <td className="max-w-xs truncate px-4 py-3 text-ink-soft">
                      {item.description ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-ink-soft">{item.unit ?? '—'}</td>
                    <td className="tabular px-4 py-3 font-medium text-ink">
                      {formatCOP(item.unit_price)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-1 text-xs font-medium rounded-full ${
                          item.is_active ? 'bg-ok-wash text-ok' : 'bg-linen-100 text-linen-600'
                        }`}
                      >
                        {item.is_active ? 'En el libro' : 'Retirado'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setEditing(item)}
                        className="rounded px-2 py-1.5 text-sm font-medium text-pine hover:bg-pine-wash"
                      >
                        Editar
                      </button>
                      {/* Destructive action kept apart, outline style, never adjacent */}
                      <button
                        type="button"
                        onClick={() => handleDelete(item)}
                        disabled={deleteItem.isLoading}
                        className="ml-3 rounded border border-lacre/40 px-2.5 py-1.5 text-sm font-medium text-lacre hover:bg-lacre-wash disabled:opacity-50"
                      >
                        Retirar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-10 text-center">
            {debouncedSearch.trim().length > 0 ? (
              <>
                <p className="text-sm font-medium text-ink">Ningún ítem coincide con esa búsqueda</p>
                <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
                  Nada en el libro coincide con «{debouncedSearch}». Pruebe con otro nombre o
                  limpie la búsqueda para ver todo el catálogo.
                </p>
                <div className="mt-4 flex justify-center">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setSearch('')
                    }}
                  >
                    Limpiar búsqueda
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-ink">El libro está en blanco</p>
                <p className="mx-auto mt-1 max-w-sm text-xs text-linen-600">
                  Agregue el primer ítem a mano o importe su lista de precios en CSV con las columnas
                  nombre, descripcion, unidad, precio_unitario.
                </p>
                <div className="mt-4 flex justify-center gap-2">
                  <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
                    <IconUpload className="h-4 w-4" />
                    Importar CSV
                  </Button>
                  <Button type="button" onClick={() => setCreating(true)}>
                    <IconPlus className="h-4 w-4" />
                    Agregar ítem
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
            Página {page + 1} de {totalPages} · {data.total} ítems
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

      {/* Create / edit modal */}
      <CatalogItemModal
        open={creating || editing !== null}
        item={editing}
        saving={editing ? updateItem.isLoading : createItem.isLoading}
        error={actionError}
        onClose={() => {
          setCreating(false)
          setEditing(null)
          setActionError(null)
        }}
        onSubmit={handleSubmit}
      />

      {/* CSV import result */}
      <Modal open={importResult !== null} title="Resultado de la importación" onClose={() => setImportResult(null)}>
        {importResult && (
          <div className="space-y-3 text-sm text-ink-soft">
            <p>
              Ítems creados: <span className="tabular font-semibold text-ink">{importResult.created}</span>
            </p>
            <p>
              Ítems actualizados: <span className="tabular font-semibold text-ink">{importResult.updated}</span>
            </p>
            {importResult.errors.length > 0 && (
              <div>
                <p className="font-medium text-lacre">Errores ({importResult.errors.length}):</p>
                <ul className="mt-1 max-h-48 list-disc overflow-y-auto pl-5 text-xs text-lacre">
                  {importResult.errors.map((err, index) => (
                    <li key={index}>{err}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex justify-end pt-2">
              <Button type="button" onClick={() => setImportResult(null)}>
                Cerrar
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
