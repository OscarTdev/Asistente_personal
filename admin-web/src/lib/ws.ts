// Dynamic WebSocket URL based on current origin
// Works in development (localhost) and production (same origin)
export function buildWsUrl(token: string): string {
  // Get the base URL from the current window location
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/ws/events?token=${token}`
}
