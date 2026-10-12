import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLogin } from '../hooks/useLogin'
import Input from '../components/ui/input'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'

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
    <div className="flex min-h-screen flex-col items-center justify-center bg-ground px-4">
      <div className="w-full max-w-sm">
        {/* The hotel letterhead */}
        <div className="rounded-t-lg bg-pine px-6 pb-5 pt-7">
          <div className="text-xl font-bold tracking-[0.24em] text-ground">AURA</div>
          <div className="mt-1 text-[0.6875rem] font-semibold uppercase tracking-[0.09em] text-linen-300">
            Asistente por WhatsApp
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-b-lg border border-t-0 border-linen-200 bg-panel p-6">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink-soft">
              Correo electrónico
            </label>
            <Input
              id="email"
              type="email"
              value={email}
              onChangeValue={setEmail}
              autoComplete="email"
              placeholder="admin@tunegocio.com"
              required
              disabled={loading}
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink-soft">
              Contraseña
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChangeValue={setPassword}
              autoComplete="current-password"
              placeholder="••••••••"
              required
              disabled={loading}
            />
          </div>
          <ErrorSlip message={error} />
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Ingresando…' : 'Iniciar sesión'}
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-linen-600">
          Panel de administración · {new Date().getFullYear()}
        </p>
      </div>
    </div>
  )
}
