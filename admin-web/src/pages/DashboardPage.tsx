import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useEvents } from '../hooks/useEvents'
import { MessageFeed } from '../components/MessageFeed'

export default function DashboardPage() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const botName = user?.bot_name ?? 'Aura'

  const { events, status } = useEvents(
    token,
    () => {
      logout()
      navigate('/login')
    }
  )

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="text-lg font-medium text-gray-900">
              Panel de {botName}
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-sm text-gray-600">
                {user?.email ?? 'Desconocido'}
              </div>
              <button
                onClick={() => {
                  logout()
                  navigate('/login')
                }}
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                Cerrar sesión
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Connection status badge */}
          <div className="mb-6 flex items-center space-x-3">
            <div
              className={`px-2 py-1 text-xs font-medium rounded-full ${
                status === 'open'
                  ? 'bg-green-100 text-green-800'
                  : status === 'connecting'
                  ? 'bg-yellow-100 text-yellow-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {status === 'open' ? 'Conectado' : status === 'connecting' ? 'Reconectando…' : 'Desconectado'}
            </div>
          </div>

          {/* Message feed */}
          <MessageFeed events={events} />
        </div>
      </main>
    </div>
  )
}