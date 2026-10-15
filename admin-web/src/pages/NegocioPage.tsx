// Mi negocio: la identidad del asistente de ESTE dueño — logo que va en
// los PDFs, y más adelante pie de página y datos bancarios.
// (El Admin de la plataforma es otra cosa: los clientes del dueño global.)

import Card from '../components/ui/card'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'
import { useAuth } from '../auth/AuthContext'
import {
  useBranding,
  useDeleteBrandingLogo,
  useUploadBrandingLogo,
} from '../hooks/useBranding'
import { useRef, useState } from 'react'

function LogoCard() {
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
    <Card className="p-5">
      <h2 className="mb-1 text-sm font-semibold text-ink">Logo del negocio</h2>
      <p className="mb-4 text-xs text-linen-600">
        Aparece en el encabezado de tus cotizaciones y cuentas de cobro
        (PNG, JPEG o WebP, máx 2 MB).
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

export default function NegocioPage() {
  const { user } = useAuth()
  const botName = user?.bot_name ?? 'Aura'

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Mi negocio</h1>
        <p className="mt-1 text-sm text-linen-600">
          La identidad de {botName} ante tus clientes: cómo se ven tus
          documentos y cómo se presenta tu asistente.
        </p>
      </div>

      <LogoCard />

      <p className="mt-4 text-xs text-linen-600">
        Próximamente aquí: pie de página de los PDFs, color del encabezado y
        datos bancarios para las cuentas de cobro.
      </p>
    </div>
  )
}
