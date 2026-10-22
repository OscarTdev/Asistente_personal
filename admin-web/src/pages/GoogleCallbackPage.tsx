// Callback de Google OAuth: Google vuelve aquí con ?code=...&state=...
// La página canjea el code contra el backend y vuelve a Mi negocio.

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'
import { useGoogleCallback } from '../hooks/useGoogle'

export default function GoogleCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const callback = useGoogleCallback()
  const [error, setError] = useState<string | null>(null)
  const startedRef = useRef(false)

  const code = params.get('code')
  const state = params.get('state')
  const googleError = params.get('error')

  useEffect(() => {
    // Solo una vez: StrictMode monta dos veces en desarrollo
    if (startedRef.current) return
    startedRef.current = true

    if (googleError === 'access_denied') {
      setError('Cancelaste el permiso en Google. Puedes volver a intentarlo.')
      return
    }
    if (!code || !state) {
      setError('Google no devolvió los datos de la conexión.')
      return
    }
    callback.mutate(
      { code, state },
      {
        onError: (err) => setError(err.message),
      }
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connectedEmail = callback.data?.google_email

  useEffect(() => {
    if (!connectedEmail) return
    const timer = setTimeout(() => navigate('/negocio', { replace: true }), 1800)
    return () => clearTimeout(timer)
  }, [connectedEmail, navigate])

  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center px-4 text-center">
      {connectedEmail ? (
        <>
          <div className="mb-3 text-5xl">🎉</div>
          <h1 className="mb-1 text-xl font-semibold text-ink">
            Cuenta de Google conectada
          </h1>
          <p className="mb-4 text-sm text-linen-600">
            Conectada como <span className="font-medium">{connectedEmail}</span>.
            Volviendo a Mi negocio…
          </p>
        </>
      ) : error ? (
        <>
          <div className="mb-3 text-5xl">😕</div>
          <h1 className="mb-3 text-xl font-semibold text-ink">
            No pude conectar tu cuenta
          </h1>
          <ErrorSlip message={error} />
          <div className="mt-4">
            <Button type="button" onClick={() => navigate('/negocio')}>
              Volver a Mi negocio
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="skel mb-3 h-12 w-12 rounded-full" />
          <p className="text-sm text-linen-600">Conectando tu cuenta de Google…</p>
        </>
      )}
    </div>
  )
}
