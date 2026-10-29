import { useState, useId } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Card } from '../components/ui/card'
import { Button } from '../components/ui/button'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { ErrorSlip } from '../components/ui/error-slip'
import { IconShield, IconEye, IconEyeOff, IconCheck } from '../components/ui/icons'
import { setPasswordRequest, ApiError } from '../lib/api'

export default function SetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const passwordId = useId()
  const confirmPasswordId = useId()

  const isLengthValid = password.length >= 8
  const isMatchValid = password.length > 0 && password === confirmPassword

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!token) {
      setError('Enlace inválido o incompleto. Solicita uno nuevo al administrador.')
      return
    }

    if (!isLengthValid) {
      setError('La contraseña debe tener al menos 8 caracteres.')
      return
    }

    if (!isMatchValid) {
      setError('Las contraseñas no coinciden.')
      return
    }

    setLoading(true)
    try {
      const response = await setPasswordRequest(token, password)
      setSuccess(true)

      // Si el backend devolvió access_token y user, iniciamos sesión de inmediato
      if (response.access_token && response.user) {
        localStorage.setItem('asistente_token', response.access_token)
        localStorage.setItem('asistente_user', JSON.stringify(response.user))
        setTimeout(() => {
          window.location.assign('/')
        }, 1200)
      } else {
        setTimeout(() => {
          navigate('/login')
        }, 2000)
      }
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Ocurrió un error al configurar tu contraseña.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="flex min-h-screen items-center justify-center p-4"
      style={{ background: 'var(--color-bg-base)' }}
    >
      <div className="w-full max-w-md animate-fade-in">
        {/* Branding */}
        <div className="mb-8 text-center">
          <div
            className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl text-xl font-bold shadow-lg mb-4"
            style={{
              background: 'linear-gradient(135deg, var(--color-brand-magenta), var(--color-brand-rose))',
              color: '#fff',
            }}
          >
            A
          </div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: 'var(--color-ink)' }}>
            Bienvenido a tu Asistente
          </h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
            Configura tu contraseña de acceso para entrar a tu panel de control
          </p>
        </div>

        <Card className="p-6 sm:p-8" style={{ border: '1px solid var(--color-border-default)', background: 'var(--color-surface)' }}>
          {success ? (
            <div className="text-center py-6">
              <div
                className="mx-auto flex h-12 w-12 items-center justify-center rounded-full mb-4"
                style={{ background: 'var(--color-ok-wash, rgba(34,197,94,0.15))', color: 'var(--color-ok, #22c55e)' }}
              >
                <IconCheck className="h-6 w-6" />
              </div>
              <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>
                ¡Contraseña configurada!
              </h2>
              <p className="mt-2 text-sm" style={{ color: 'var(--color-ink-muted)' }}>
                Ingresando a tu panel de control...
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {!token && (
                <div
                  className="rounded-lg p-3 text-sm mb-4"
                  style={{
                    background: 'var(--color-danger-wash)',
                    color: 'var(--color-danger)',
                    border: '1px solid var(--color-danger-border)',
                  }}
                >
                  Este enlace no contiene un token válido. Solicita un enlace nuevo a través de WhatsApp o a tu administrador.
                </div>
              )}

              {error && <ErrorSlip message={error} />}

              {/* Nueva contraseña */}
              <div>
                <Label htmlFor={passwordId} style={{ color: 'var(--color-ink)' }}>
                  Nueva contraseña
                </Label>
                <div className="relative mt-1">
                  <Input
                    id={passwordId}
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Mínimo 8 caracteres"
                    required
                    disabled={loading || !token}
                    className="pr-10"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-stone-400 hover:text-stone-600 dark:hover:text-stone-200"
                    tabIndex={-1}
                  >
                    {showPassword ? <IconEyeOff className="h-4 w-4" /> : <IconEye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Confirmar contraseña */}
              <div>
                <Label htmlFor={confirmPasswordId} style={{ color: 'var(--color-ink)' }}>
                  Confirmar contraseña
                </Label>
                <div className="mt-1">
                  <Input
                    id={confirmPasswordId}
                    type={showPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repite la contraseña"
                    required
                    disabled={loading || !token}
                  />
                </div>
              </div>

              {/* Validación visual de requisitos */}
              <div className="space-y-1.5 rounded-lg p-3 text-xs" style={{ background: 'var(--color-raised)' }}>
                <div className="flex items-center gap-2" style={{ color: isLengthValid ? 'var(--color-ok, #22c55e)' : 'var(--color-ink-muted)' }}>
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${isLengthValid ? 'bg-emerald-500' : 'bg-stone-400'}`} />
                  Al menos 8 caracteres
                </div>
                <div className="flex items-center gap-2" style={{ color: isMatchValid ? 'var(--color-ok, #22c55e)' : 'var(--color-ink-muted)' }}>
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${isMatchValid ? 'bg-emerald-500' : 'bg-stone-400'}`} />
                  Las contraseñas coinciden
                </div>
              </div>

              <Button
                type="submit"
                disabled={loading || !token || !isLengthValid || !isMatchValid}
                className="w-full flex items-center justify-center gap-2 py-2.5 font-medium"
              >
                <IconShield className="h-4 w-4" />
                {loading ? 'Guardando contraseña…' : 'Activar cuenta y entrar'}
              </Button>

              <div className="text-center pt-2">
                <Link
                  to="/login"
                  className="text-xs hover:underline"
                  style={{ color: 'var(--color-ink-muted)' }}
                >
                  ¿Ya tienes contraseña? Inicia sesión aquí
                </Link>
              </div>
            </form>
          )}
        </Card>
      </div>
    </div>
  )
}
