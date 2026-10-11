import { LoginResponse } from '../types'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('asistente_token')
  if (!token) {
    return {}
  }
  return {
    Authorization: `Bearer ${token}`,
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      ...init.headers,
      ...authHeaders(),
    },
  })

  if (!response.ok) {
    let errorMessage = 'Error desconocido'
    try {
      const errorData = await response.json()
      errorMessage = errorData.detail || errorData.message || 'Error desconocido'
    } catch (e) {
      // Ignore
    }
    throw new ApiError(errorMessage, response.status)
  }

  return response.json()
}

export async function loginRequest(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>('/auth/login', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ email, password }),
  })
}