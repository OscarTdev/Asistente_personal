// Página parametrizada para los servicios operativos del técnico:
// inventario, mantenimiento, garantías, gastos y obra. Una sola página
// que adapta sus columnas al servicio — el code-judo: en vez de 5
// páginas duplicadas, una que se ajusta.

import { Link } from 'react-router-dom'
import { useState } from 'react'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Input from '../components/ui/input'
import ErrorSlip from '../components/ui/error-slip'
import { IconArrowLeft } from '../components/ui/icons'

// ── Configuración por servicio ─────────────────────────────────────────────

interface Column {
  key: string
  label: string
  width?: string
}

const CONFIG: Record<
  string,
  {
    title: string
    subtitle: string
    endpoint: string
    columns: Column[]
    emptyMessage: string
  }
> = {
  inventory: {
    title: 'Inventario',
    subtitle:
      'Materiales del negocio: qué hay, cuánto queda y qué está bajo el mínimo.',
    endpoint: 'inventory',
    columns: [
      { key: 'name', label: 'Material' },
      { key: 'quantity', label: 'Cantidad' },
      { key: 'unit', label: 'Unidad' },
      { key: 'min_quantity', label: 'Mínimo' },
    ],
    emptyMessage:
      'Sin materiales aún. Agrégalos por chat: «tengo 100 metros de cable THHN #12».',
  },
  maintenance: {
    title: 'Mantenimiento preventivo',
    subtitle:
      'Avisos periódicos a tus clientes: el bot les escribe cuando toca.',
    endpoint: 'maintenance',
    columns: [
      { key: 'description', label: 'Mantenimiento' },
      { key: 'contact_name', label: 'Cliente' },
      { key: 'next_due', label: 'Próximo' },
      { key: 'frequency_days', label: 'Cada (días)' },
    ],
    emptyMessage:
      'Sin mantenimientos aún. Agrégalos por chat: «recuérdale a Juliana limpiar el aire cada 6 meses».',
  },
  warranties: {
    title: 'Garantías',
    subtitle: 'Qué se instaló, para quién y hasta cuándo cubre la garantía.',
    endpoint: 'warranties',
    columns: [
      { key: 'item', label: 'Instalado' },
      { key: 'contact_name', label: 'Cliente' },
      { key: 'installed_at', label: 'Instalado el' },
      { key: 'expires_at', label: 'Vence el' },
    ],
    emptyMessage:
      'Sin garantías registradas. Agrégalas por chat: «garantía del aire acondicionado de María, 1 año».',
  },
  expenses: {
    title: 'Finanzas personales',
    subtitle: 'Tus gastos del negocio: materiales, transporte, comida, etc.',
    endpoint: 'expenses',
    columns: [
      { key: 'description', label: 'Gasto' },
      { key: 'category', label: 'Categoría' },
      { key: 'amount', label: 'Monto' },
      { key: 'expense_date', label: 'Fecha' },
    ],
    emptyMessage:
      'Sin gastos aún. Regístralos por chat: «gasté 20 mil en gasolina».',
  },
  'site-log': {
    title: 'Seguimiento de obra',
    subtitle: 'Bitácora de tus trabajos en sitio, día a día.',
    endpoint: 'site-log',
    columns: [
      { key: 'title', label: 'Obra' },
      { key: 'contact_name', label: 'Cliente' },
      { key: 'status', label: 'Estado' },
    ],
    emptyMessage:
      'Sin obras registradas. Empieza por chat: «nueva obra: instalación en casa de Juliana».',
  },
}

// ── Formato de valores ────────────────────────────────────────────────────

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('es-CO', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function formatCOP(value: number): string {
  return `$${value.toLocaleString('es-CO')}`
}

function formatCell(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (key === 'amount') return formatCOP(Number(value))
  if (key.includes('_at') || key === 'next_due' || key === 'expense_date') {
    return formatDate(String(value))
  }
  if (key === 'quantity') return String(value)
  if (key === 'frequency_days') return String(value)
  return String(value)
}

// ── Página ────────────────────────────────────────────────────────────────

export default function ServiceDataPage({ serviceKey }: { serviceKey: string }) {
  const config = CONFIG[serviceKey]
  const [data, setData] = useState<Record<string, unknown>[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  // Fetch al montar (sin react-query para mantener la página ligera)
  useState(() => {
    const token = localStorage.getItem('asistente_token')
    fetch(`/api/v1/service-data/${config.endpoint}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Error ${res.status}`)
        return res.json()
      })
      .then((json) => {
        setData(json)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  })

  if (!config) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm">Servicio no encontrado.</p>
      </div>
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

      <div className="mt-3 mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          {config.title}
        </h1>
        <p className="mt-1 text-sm text-linen-600">{config.subtitle}</p>
      </div>

      {error && (
        <div className="mb-4">
          <ErrorSlip message={error} />
        </div>
      )}

      <Card className="overflow-hidden">
        {loading ? (
          <div className="divide-y divide-linen-100">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex h-12 items-center gap-4 px-4">
                <div className="skel h-4 w-1/4" />
                <div className="skel ml-auto h-4 w-24" />
              </div>
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-medium text-ink">{config.emptyMessage}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead-edge bg-linen-50 text-left">
                  {config.columns.map((col) => (
                    <th
                      key={col.key}
                      className="plate-label px-4 py-3 font-semibold"
                      style={col.width ? { width: col.width } : undefined}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr
                    key={String(row.id ?? i)}
                    className="border-b border-linen-100 transition-colors last:border-0 hover:bg-linen-50"
                  >
                    {config.columns.map((col) => (
                      <td
                        key={col.key}
                        className={`px-4 py-3 ${
                          col.key === config.columns[0].key
                            ? 'font-medium text-ink'
                            : 'text-ink-soft'
                        }`}
                      >
                        {formatCell(col.key, row[col.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="mt-4 text-xs text-linen-600">
        También puedes gestionar este servicio por chat con tu asistente —
        es la forma más rápida.
      </p>
    </div>
  )
}
