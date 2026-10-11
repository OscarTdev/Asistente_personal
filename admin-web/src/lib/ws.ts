export function buildWsUrl(token: string): string {
  return `ws://localhost:8000/ws/events?token=${token}`
}
