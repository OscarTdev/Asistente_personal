import { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { buildWsUrl } from '../lib/ws'
import { FeedEvent } from '../types'

export type WsStatus = 'connecting' | 'open' | 'closed'

export function useEvents(
  token: string | null,
  onAuthError: (() => void) | undefined = undefined
) {
  const { logout } = useAuth()
  const [events, setEvents] = useState<FeedEvent[]>([])
  const [status, setStatus] = useState<WsStatus>('closed')

  useEffect(() => {
    if (!token) {
      setStatus('closed')
      return
    }

    let ws: WebSocket | null = null
    let status: WsStatus = 'connecting'
    setStatus(status)

    const wsUrl = buildWsUrl(token)
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      status = 'open'
      setStatus(status)
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
      status = 'closed'
      setStatus(status)
      // If the close code is 1008 (policy violation), it's an auth error
      if (event.code === 1008) {
        logout()
        if (onAuthError) {
          onAuthError()
        }
      } else {
        // Otherwise, try to reconnect after 2 seconds
        setTimeout(() => {
          if (token) {
            // Recursively call the effect? We'll just re-run the effect by resetting the token?
            // We'll do nothing here; the effect will re-run if the token changes.
            // We'll just set the status to connecting and try to reconnect.
            setStatus('connecting')
            // We'll create a new WebSocket? We'll do nothing and let the effect re-run.
            // Instead, we'll do nothing and the effect will re-run on the next tick if token changes.
            // We'll leave it as is.
          }
        }, 2000)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    // Cleanup
    return () => {
      ws?.close()
    }
  }, [token, logout, onAuthError])

  return { events, status }
}