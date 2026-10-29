// Mi negocio: la identidad del asistente de ESTE dueño — logo que va en
// los PDFs, y más adelante pie de página y datos bancarios.
// (El Admin de la plataforma es otra cosa: los clientes del dueño global.)

import { Card } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { ErrorSlip } from "../components/ui/error-slip"
import { useAuth } from '../auth/AuthContext'
import {
  useBranding,
  useDeleteBrandingLogo,
  useUploadBrandingLogo,
} from '../hooks/useBranding'
import {
  useGmailTest,
  useGoogleAuthorize,
  useGoogleDisconnect,
  useGoogleStatus,
} from '../hooks/useGoogle'
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

function GoogleCard() {
  const { data, isLoading, error } = useGoogleStatus()
  const authorize = useGoogleAuthorize()
  const disconnect = useGoogleDisconnect()
  const [note, setNote] = useState<string | null>(null)
  const [testOpen, setTestOpen] = useState(false)

  // Prueba de la conexión: los 3 correos más recientes (solo lectura)
  const gmailTest = useGmailTest(testOpen)

  const handleConnect = () => {
    setNote(null)
    authorize.mutate(undefined, {
      onSuccess: (result) => {
        window.location.href = result.authorization_url
      },
      onError: (err) => setNote(`Error: ${err.message}`),
    })
  }

  const handleDisconnect = () => {
    if (!window.confirm('¿Desconectar tu cuenta de Google? El asistente dejará de leer tu correo y tu agenda.')) {
      return
    }
    setTestOpen(false)
    setNote(null)
    disconnect.mutate(undefined, {
      onSuccess: () => setNote('Cuenta desconectada ✓'),
      onError: (err) => setNote(`Error: ${err.message}`),
    })
  }

  return (
    <Card className="p-5">
      <h2 className="mb-1 text-sm font-semibold text-ink">Cuenta de Google</h2>
      <p className="mb-4 text-xs text-linen-600">
        Conecta tu Gmail, Calendar, Sheets y Docs para que tu asistente pueda
        resumirte el correo, agendar visitas y exportar tus gastos. Nunca
        envía nada sin tu confirmación.
      </p>
      {error && (
        <div className="mb-3">
          <ErrorSlip message={error.message} />
        </div>
      )}
      {isLoading ? (
        <div className="skel h-10 w-full" />
      ) : data?.connected ? (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <span className="inline-flex h-2 w-2 rounded-full bg-ok" />
            <p className="text-sm font-medium text-ink">
              Conectada: {data.google_email}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setTestOpen((v) => !v)}
            >
              {testOpen ? 'Ocultar' : 'Probar Gmail'}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={handleDisconnect}
              disabled={disconnect.isLoading}
            >
              {disconnect.isLoading ? 'Desconectando…' : 'Desconectar'}
            </Button>
          </div>
          {testOpen && (
            <div className="mt-3">
              {gmailTest.isLoading ? (
                <div className="skel h-16 w-full" />
              ) : gmailTest.error ? (
                <ErrorSlip message={gmailTest.error.message} />
              ) : gmailTest.data && gmailTest.data.length > 0 ? (
                <ul className="space-y-2">
                  {gmailTest.data.map((m, i) => (
                    <li key={i} className="rounded border border-linen-200 p-2">
                      <p className="text-xs font-medium text-ink">
                        {m.subject || '(sin asunto)'}
                      </p>
                      <p className="text-xs text-linen-600">{m.sender}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-linen-600">
                  Bandeja vacía: conexión funcionando ✓
                </p>
              )}
            </div>
          )}
        </div>
      ) : data?.configured ? (
        <Button
          type="button"
          size="sm"
          onClick={handleConnect}
          disabled={authorize.isLoading}
        >
          {authorize.isLoading ? 'Abriendo Google…' : 'Conectar Google'}
        </Button>
      ) : (
        <p className="rounded border border-dashed border-linen-300 p-3 text-xs text-linen-600">
          Falta un paso de plataforma: crear las credenciales de Google
          (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET) siguiendo la guía
          <code className="mx-1 rounded bg-linen-100 px-1 py-0.5">docs/GOOGLE.md §1</code>
          y añadirlas al archivo .env de la raíz. Cuando estén, aquí
          aparecerá el botón para conectar tu cuenta.
        </p>
      )}
      {note && (
        <p className={`mt-3 text-xs ${note.startsWith('Error') ? 'text-lacre' : 'text-ok'}`}>
          {note}
        </p>
      )}
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

      <div className="flex flex-col gap-4">
        <LogoCard />
        <GoogleCard />
      </div>

      <p className="mt-4 text-xs text-linen-600">
        Próximamente aquí: pie de página de los PDFs, color del encabezado y
        datos bancarios para las cuentas de cobro.
      </p>
    </div>
  )
}
