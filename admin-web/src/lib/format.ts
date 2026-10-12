// Formatting helpers shared across pages.

export function formatCOP(value: string | number): string {
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (Number.isNaN(n)) {
    return '—'
  }
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 2,
  }).format(n)
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) {
    return '—'
  }
  return new Date(iso).toLocaleDateString('es-CO', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function round2(value: number): number {
  return Math.round(value * 100) / 100
}
