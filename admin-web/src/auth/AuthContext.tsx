import { createContext, useContext, useState, useEffect } from 'react'
import { loginRequest, impersonateTenant, fetchMe, ApiError } from '../lib/api'
import { User } from '../types'

type Theme = 'light' | 'dark' | 'system'

interface AuthContextType {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  impersonate: (tenantId: string) => Promise<void>
  stopImpersonating: () => void
  isImpersonating: boolean
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: 'light' | 'dark'
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'system'
  return (localStorage.getItem('asistente_theme') as Theme) ?? 'system'
}

function getResolvedTheme(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

function applyTheme(theme: Theme) {
  const resolved = getResolvedTheme(theme)
  document.documentElement.classList.toggle('dark', resolved === 'dark')
  localStorage.setItem('asistente_theme', theme)
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem('asistente_user')
    if (!raw) return null
    try {
      return JSON.parse(raw) as User
    } catch (e) {
      return null
    }
  })
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('asistente_token'))
  const [isImpersonating, setIsImpersonating] = useState<boolean>(() => {
    return !!localStorage.getItem('asistente_original_token')
  })
  const [theme, setThemeState] = useState<Theme>(() => getInitialTheme())
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>(() => getResolvedTheme(getInitialTheme()))

  // Apply theme on mount and when it changes
  useEffect(() => {
    applyTheme(theme)
    setResolvedTheme(getResolvedTheme(theme))
  }, [theme])

  // Listen for system theme changes
  useEffect(() => {
    if (theme !== 'system') return
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (e: MediaQueryListEvent) => {
      const resolved = e.matches ? 'dark' : 'light'
      document.documentElement.classList.toggle('dark', resolved === 'dark')
      setResolvedTheme(resolved)
    }
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme])

  // Background refresh of user profile if token is present
  useEffect(() => {
    if (token) {
      fetchMe()
        .then((updatedUser) => {
          setUser(updatedUser)
          localStorage.setItem('asistente_user', JSON.stringify(updatedUser))
          if (updatedUser.is_impersonating || localStorage.getItem('asistente_original_token')) {
            setIsImpersonating(true)
          }
        })
        .catch(() => {
          // Token expired or invalid
        })
    }
  }, [token])

  const login = async (email: string, password: string) => {
    try {
      const response = await loginRequest(email, password)
      setToken(response.access_token)
      setUser(response.user)
      setIsImpersonating(false)
      localStorage.removeItem('asistente_original_token')
      localStorage.removeItem('asistente_original_user')
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

  const impersonate = async (tenantId: string) => {
    // Preserve current credentials as original credentials
    if (!localStorage.getItem('asistente_original_token') && token && user) {
      localStorage.setItem('asistente_original_token', token)
      localStorage.setItem('asistente_original_user', JSON.stringify(user))
    }
    const response = await impersonateTenant(tenantId)
    setToken(response.access_token)
    setUser(response.user)
    setIsImpersonating(true)
    localStorage.setItem('asistente_token', response.access_token)
    localStorage.setItem('asistente_user', JSON.stringify(response.user))
  }

  const stopImpersonating = () => {
    const origToken = localStorage.getItem('asistente_original_token')
    const origUserRaw = localStorage.getItem('asistente_original_user')
    if (origToken && origUserRaw) {
      try {
        const origUser = JSON.parse(origUserRaw) as User
        setToken(origToken)
        setUser(origUser)
        setIsImpersonating(false)
        localStorage.setItem('asistente_token', origToken)
        localStorage.setItem('asistente_user', origUserRaw)
        localStorage.removeItem('asistente_original_token')
        localStorage.removeItem('asistente_original_user')
        return
      } catch (e) {
        // Fall through
      }
    }
    logout()
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    setIsImpersonating(false)
    localStorage.removeItem('asistente_token')
    localStorage.removeItem('asistente_user')
    localStorage.removeItem('asistente_original_token')
    localStorage.removeItem('asistente_original_user')
  }

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        impersonate,
        stopImpersonating,
        isImpersonating,
        theme,
        setTheme,
        resolvedTheme,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}