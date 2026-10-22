// LoginPage v2 — Dark Premium.
// Pantalla de inicio de sesión: fondo oscuro con gradiente radial,
// glassmorphism, animación de entrada, y logo con glow.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLogin } from '../hooks/useLogin'

export default function LoginPage() {
  const navigate = useNavigate()
  const { loading, error, handleLogin } = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const ok = await handleLogin(email, password)
    if (ok) {
      navigate('/')
    }
  }

  return (
    <div
      className="flex min-h-screen flex-col items-center justify-center px-4"
      style={{
        background: 'radial-gradient(ellipse at 50% 0%, rgba(124,58,237,0.15) 0%, #0a0a0f 60%)',
      }}
    >
      {/* Fondo grid sutil */}
      <div
        className="fixed inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
        }}
      />

      <div className="relative w-full max-w-sm animate-fade-in">
        {/* Logo / Header */}
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex">
            <div
              className="flex h-14 w-14 items-center justify-center rounded-2xl text-xl font-bold text-white"
              style={{
                background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
                boxShadow: '0 0 32px rgba(124,58,237,0.5)',
              }}
            >
              A
            </div>
          </div>
          <h1
            className="text-2xl font-bold"
            style={{
              background: 'linear-gradient(135deg, #f0f0ff 0%, #a78bfa 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            Aura Panel
          </h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
            Tu asistente personal por WhatsApp
          </p>
        </div>

        {/* Tarjeta de login */}
        <div
          className="card-glass rounded-2xl p-8"
          style={{
            background: 'rgba(22, 22, 31, 0.80)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="mb-2 block text-xs font-semibold uppercase tracking-wider"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                Correo electrónico
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="admin@tunegocio.com"
                required
                disabled={loading}
                className="input-field"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-2 block text-xs font-semibold uppercase tracking-wider"
                style={{ color: 'var(--color-text-tertiary)' }}
              >
                Contraseña
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                required
                disabled={loading}
                className="input-field"
              />
            </div>

            {error && (
              <div className="slip">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary btn-md w-full"
              style={{ marginTop: '8px', fontSize: '0.9375rem' }}
            >
              {loading ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                  </svg>
                  Ingresando…
                </>
              ) : (
                'Iniciar sesión'
              )}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs" style={{ color: 'var(--color-text-disabled)' }}>
          Panel de administración · {new Date().getFullYear()}
        </p>
      </div>
    </div>
  )
}
