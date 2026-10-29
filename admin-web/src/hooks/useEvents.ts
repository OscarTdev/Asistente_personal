import { useRef, useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { buildWsUrl } from '../lib/ws'
import { FeedEvent } from '../types'

export type WsStatus = 'connecting' | 'open' | 'closed'

const RECONNECT_MS = 2500

export function useEvents(
  token: string | null,
  onAuthError: (() => void) | undefined = undefined
) {
  const { logout } = useAuth()
  const [events, setEvents] = useState<FeedEvent[]>([])
  const [status, setStatus] = useState<WsStatus>('closed')
  // El callback en un ref: evita que el efecto (y el socket) se re-creen
  // en cada render del padre — solo se reconecta si cambia el token.
  const onAuthErrorRef = useRef(onAuthError)
  onAuthErrorRef.current = onAuthError

  useEffect(() => {
    if (!token) {
      setStatus('closed')
      return
    }

    let disposed = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    setStatus('connecting')

    const connect = () => {
      if (disposed) return
      ws = new WebSocket(buildWsUrl(token))

      ws.onopen = () => {
        if (!disposed) setStatus('open')
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as FeedEvent
          // Ignore the connected message
          if (data.type === 'connected') {
            return
          }
          // Prepend the new event, keeping only the last 50
          setEvents(prev => [data, ...prev.slice(0, 49)])
        } catch (e) {
          console.error('Error parsing WebSocket message:', e)
        }
      }

      ws.onclose = (event) => {
        if (disposed) return
        // 1008 (policy violation) = token inválido/expirado: cerrar sesión
        if (event.code === 1008) {
          logout()
          onAuthErrorRef.current?.()
          return
        }
        // Cualquier otra caída (backend reiniciado, red): reconectar solo
        setStatus('closed')
        reconnectTimer = setTimeout(connect, RECONNECT_MS)
      }

      ws.onerror = () => {
        // El onclose maneja la reconexión; aquí solo evitamos el ruido rojo
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [token, logout])

  return { events, status }
}
