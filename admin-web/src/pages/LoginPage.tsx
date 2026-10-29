// LoginPage v3 — Impecable. Clean, centered, glassmorphism card.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLogin } from '../hooks/useLogin'
import { authorizeGoogleLogin } from '../lib/api'
import { IconShield } from '@/components/ui/icons'

export default function LoginPage() {
  const navigate = useNavigate()
  const botName = new URLSearchParams(window.location.search).get('bot')?.trim() || 'Aura'
  const { loading, error, handleLogin } = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleError, setGoogleError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const ok = await handleLogin(email, password)
    if (ok) {
      navigate('/')
    }

    const handleGoogleLogin = async () => {
      if (!email.trim()) {
        setGoogleError('Escribe primero el correo de tu cuenta.')
        return
      }
      setGoogleLoading(true)
      setGoogleError(null)
      try {
        const { authorization_url } = await authorizeGoogleLogin(email.trim())
        window.location.assign(authorization_url)
      } catch (err) {
        setGoogleError(err instanceof Error ? err.message : 'No se pudo iniciar Google')
        setGoogleLoading(false)
      }
    }
  }

  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center px-4"
      style={{
        background: 'radial-gradient(ellipse at 50% 0%, rgba(124,58,237,0.12) 0%, #0a0a0f 60%)',
      }}
    >
      {/* Subtle grid pattern */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)
          `,
          backgroundSize: '56px 56px',
        }}
      />

      <div className="relative w-full max-w-md animate-fade-in">
        {/* Header */}
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex">
            <div
              className="flex h-12 w-12 items-center justify-center rounded-xl text-lg font-bold text-white"
              style={{
                background: 'linear-gradient(135deg, var(--color-brand-magenta), var(--color-brand-rose))',
                boxShadow: '0 0 24px rgba(232,67,147,0.4)',
              }}
            >
              <IconShield className="h-6 w-6" />
            </div>
          </div>
          <h1
            className="text-2xl font-semibold"
            style={{
              background: 'linear-gradient(135deg, #f0f0ff 0%, #a78bfa 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            {botName} Panel
          </h1>
          <p className="mt-1 text-sm" style={{ color: '#D4C8BE' }}>
            Panel de administración de {botName}
          </p>
        </div>

        {/* Login Card - Glassmorphism */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: 'rgba(22, 22, 31, 0.75)',
            border: '1px solid rgba(255,255,255,0.08)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 24px 48px rgba(0,0,0,0.3)',
          }}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label
                htmlFor="email"
                className="mb-2 block text-xs font-semibold uppercase tracking-wider"
                style={{ color: '#D4C8BE' }}
              >
                Correo electrónico
              </label>
              <div className="relative">
                <svg
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4"
                  style={{ color: '#8A7A72' }}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.75}
                    d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                  />
                </svg>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="admin@tunegocio.com"
                  required
                  disabled={loading}
                  className="input-field w-full pl-10 pr-4 h-11"
                  style={{
                    background: 'rgba(15,15,25,0.85)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: '#F5F0E8',
                  }}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-xs font-semibold uppercase tracking-wider"
                style={{ color: '#D4C8BE' }}
              >
                Contraseña
              </label>
              <div className="relative">
                <svg
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4"
                  style={{ color: '#8A7A72' }}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.75}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-5M12 7a4 4 0 110 8 4 4 0 010-8z"
                  />
                </svg>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  className="input-field w-full pl-10 pr-12 h-11"
                  style={{
                    background: 'rgba(15,15,25,0.85)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: '#F5F0E8',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-sm"
                  style={{ color: '#D4C8BE' }}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  {showPassword ? (
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75} aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L3 3l3.59 3.59m0 0l3.59 3.59" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.75} aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div
                className="slip"
                style={{
                  background: 'rgba(248,113,113,0.12)',
                  border: '1px solid rgba(248,113,113,0.30)',
                  color: '#F87171',
                }}
              >
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary btn-lg w-full"
              style={{
                marginTop: '8px',
                fontSize: '0.9375rem',
                fontWeight: 600,
                letterSpacing: '0.02em',
              }}
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.25} aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                  </svg>
                  Ingresando…
                </>
              ) : (
                'Iniciar sesión'
              )}
            </button>
            <div className="flex items-center gap-3 py-1 text-xs" style={{ color: '#8A7A72' }}>
              <span className="h-px flex-1 bg-white/10" />
              o continúa con
              <span className="h-px flex-1 bg-white/10" />
            </div>
            <button
              type="button"
              onClick={handleGoogleLogin}
              disabled={loading || googleLoading}
              className="btn btn-lg w-full"
              style={{ background: '#fff', color: '#202124', fontWeight: 600 }}
            >
              {googleLoading ? 'Abriendo Google…' : 'Continuar con Google'}
            </button>
            {googleError && (
              <div className="slip" style={{ color: '#F87171' }}>{googleError}</div>
            )}
          </form>
        </div>

        <p className="mt-6 text-center text-xs" style={{ color: '#8A7A72' }}>
          Panel de administración · {new Date().getFullYear()}
        </p>
      </div>
    </div>
  )
}