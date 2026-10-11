import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { loginRequest, ApiError } from '../lib/api'

export function useLogin() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { login } = useAuth()

  const handleLogin = async (email: string, password: string): Promise<boolean> => {
    setLoading(true)
    setError(null)
    try {
      await login(email, password)
      return true
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Error desconocido')
      }
      return false
    } finally {
      setLoading(false)
    }
  }

  return { loading, error, handleLogin }
}