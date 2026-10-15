// Administración de la plataforma: planes y precios del negocio.
// Solo administradores de la plataforma (is_platform_admin).

import { useEffect, useRef, useState } from 'react'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Input from '../components/ui/input'
import ErrorSlip from '../components/ui/error-slip'
import { useAuth } from '../auth/AuthContext'
import { usePlanPrices, useUpdatePlanPrice } from '../hooks/usePlans'
import { useBranding, useDeleteBrandingLogo, useUploadBrandingLogo } from '../hooks/useBranding'
import { PlanPrice } from '../types'

function formatCOP(value: number): string {
  return `$${value.toLocaleString('es-CO')}`
}

function PlanRow({ plan }: { plan: PlanPrice }) {
  const update = useUpdatePlanPrice()
  const [price, setPrice] = useState(String(plan.price_cop))
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    setPrice(String(plan.price_cop))
  }, [plan.price_cop])

  const parsed = Number(price)
  const dirty = Number.isInteger(parsed) && parsed !== plan.price_cop

  const handleSave = () => {
    if (!Number.isInteger(parsed) || parsed < 0) {
      setNote('El precio debe ser un entero mayor o igual a 0')
      return
    }
    setNote(null)
    update.mutate(
      { plan: plan.plan, priceCop: parsed },
      {
        onSuccess: () => setNote('Precio actualizado ✓'),
        onError: (err) => setNote(`Error: ${err.message}`),
      }
    )
  }

  return (
    <div className="ficha flex flex-wrap items-end gap-3 px-4 py-3">
      <div className="min-w-[140px] flex-1">
        <div className="text-sm font-semibold text-ink">{plan.label}</div>
        <div className="plate-label">{plan.plan}</div>
      </div>
      {plan.is_overridden && (
        <span className="mb-1.5 rounded-full bg-pine-wash px-2 py-1 text-xs font-medium text-pine">
          Personalizado
        </span>
      )}
      <div className="w-40">
        <label className="plate-label mb-1 block" htmlFor={`price-${plan.plan}`}>
          Precio (COP)
        </label>
        <Input
          id={`price-${plan.plan}`}
          value={price}
          onChangeValue={setPrice}
          inputMode="numeric"
          aria-label={`Precio del plan ${plan.label} en pesos colombianos`}
        />
      </div>
      <div className="mb-3 text-sm tabular text-linen-600">
        hoy: <span className="font-medium text-ink-soft">{formatCOP(plan.price_cop)}</span>
      </div>
      <Button
        type="button"
        size="sm"
        onClick={handleSave}
        disabled={!dirty || update.isLoading}
      >
        {update.isLoading ? 'Guardando…' : 'Guardar'}
      </Button>
      {note && (
        <p
          className={`w-full text-xs ${
            note.startsWith('Error') || note.startsWith('El precio')
              ? 'text-lacre'
              : 'text-ok'
          }`}
        >
          {note}
        </p>
      )}
    </div>
  )
}

function BrandingCard() {
  const { data, isLoading, error } = useBranding()
  const upload = useUploadBrandingLogo()
  const remove = useDeleteBrandingLogo()
  const [note, setNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setNote(null)
    upload.mutate(file, {
      onSuccess: () => setNote('Logo actualizado ✓'),
      onError: (err) => setNote(`Error: ${err.message}`),
    })
    event.target.value = '' // permitir volver a subir el mismo archivo
  }

  const handleRemove = () => {
    if (
      !window.confirm(
        '¿Quitar el logo? Los PDFs volverán al encabezado solo con texto.'
      )
    ) {
      return
    }
    remove.mutate(undefined, {
      onSuccess: () => setNote('Logo quitado ✓'),
      onError: (err) => setNote(`Error: ${err.message}`),
    })
  }

  return (
    <Card className="mb-6 p-5">
      <h2 className="mb-1 text-sm font-semibold text-ink">Marca del negocio</h2>
      <p className="mb-4 text-xs text-linen-600">
        El logo aparece en el encabezado de las cotizaciones y cuentas de
        cobro (PNG, JPEG o WebP, máx 2 MB).
      </p>
      {error && (
        <div className="mb-3">
          <ErrorSlip message={error.message} />
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4">
        {isLoading ? (
          <div className="skel h-16 w-32" />
        ) : data?.has_logo && data.logo_data_url ? (
          <img
            src={data.logo_data_url}
            alt="Logo del negocio"
            className="h-16 w-auto max-w-[200px] rounded border border-linen-200 bg-white object-contain p-1"
          />
        ) : (
          <div className="flex h-16 w-32 items-center justify-center rounded border border-dashed border-linen-300 text-xs text-linen-600">
            Sin logo
          </div>
        )}
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={upload.isLoading || remove.isLoading}
          >
            {upload.isLoading
              ? 'Subiendo…'
              : data?.has_logo
                ? 'Cambiar logo'
                : 'Subir logo'}
          </Button>
          {data?.has_logo && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleRemove}
              disabled={upload.isLoading || remove.isLoading}
            >
              {remove.isLoading ? 'Quitando…' : 'Quitar'}
            </Button>
          )}
        </div>
        {note && (
          <p className={`w-full text-xs ${note.startsWith('Error') ? 'text-lacre' : 'text-ok'}`}>
            {note}
          </p>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={handleFile}
        />
      </div>
    </Card>
  )
}

export default function AdminPage() {
  const { user } = useAuth()
  const { data, isLoading, error } = usePlanPrices()

  if (!user?.is_platform_admin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">
          Solo el administrador de la plataforma puede ver esta sección.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Administración</h1>
        <p className="mt-1 text-sm text-linen-600">
          Planes de suscripción y precios que cobra la plataforma.
        </p>
      </div>

      {error && (
        <div className="mb-4">
          <ErrorSlip message={error.message} />
        </div>
      )}

      <BrandingCard />

      <Card className="p-5">
        <h2 className="mb-1 text-sm font-semibold text-ink">Planes y precios</h2>
        <p className="mb-4 text-xs text-linen-600">
          El precio vigente se usa al generar el link de pago y al validar que
          el pago recibido corresponde al plan. Los cambios aplican para links
          nuevos; los ya emitidos se validan con el precio con el que se cobraron.
        </p>
        {isLoading ? (
          <div className="space-y-2">
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
            <div className="skel h-16 w-full" />
          </div>
        ) : (
          <div className="space-y-2">
            {(data ?? []).map((plan) => (
              <PlanRow key={plan.plan} plan={plan} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
