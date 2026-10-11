import { createContext, useContext, useState, useEffect } from 'react'
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
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)

  const login = async (email: string, password: string) => {
    try {
      const response = await loginRequest(email, password)
      setToken(response.access_token)
      setUser(response.user)
      // Store the token in localStorage
      localStorage.setItem('asistente_token', response.access_token)
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
  }

  // On component mount, check if there's a token in localStorage
  useEffect(() => {
    const storedToken = localStorage.getItem('asistente_token')
    if (storedToken) {
      setToken(storedToken)
      // TODO: We could validate the token by making a request to the server
      // For now, we'll assume it's valid and set the user to a placeholder
      // In a real app, we would fetch the user info from the token
      // We'll leave the user as null and rely on the token being present
      // The dashboard will show the bot_name from the token? Actually, we need the user info.
      // We'll leave it as null for now and handle it in the dashboard.
    }
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}