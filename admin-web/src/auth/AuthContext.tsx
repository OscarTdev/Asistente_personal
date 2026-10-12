import { createContext, useContext, useState } from 'react'
import { loginRequest, ApiError } from '../lib/api'
import { User } from '../types'

interface AuthContextType {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Restore the session SYNCHRONOUSLY from localStorage so the very first
  // render is authenticated. Restoring in an effect causes a redirect race:
  // a full page load of /catalog first renders as logged-out, matches the
  // splat route, and bounces to /login, then to / once the user restores.
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem('asistente_user')
    if (!raw) {
      return null
    }
    try {
      return JSON.parse(raw) as User
    } catch (e) {
      return null
    }
  })
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('asistente_token'))

  const login = async (email: string, password: string) => {
    try {
      const response = await loginRequest(email, password)
      setToken(response.access_token)
      setUser(response.user)
      // Store the token and the user so a page refresh keeps the session
      localStorage.setItem('asistente_token', response.access_token)
      localStorage.setItem('asistente_user', JSON.stringify(response.user))
    } catch (error) {
      if (error instanceof ApiError) {
        throw error
      } else {
        throw new ApiError('Error desconocido', 500)
      }
    }
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('asistente_token')
    localStorage.removeItem('asistente_user')
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}