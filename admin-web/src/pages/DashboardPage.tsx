// El mostrador del panel: estado del asistente, métricas reales del negocio
// (clientes, cotizaciones, mensajes, servicios más demandados) y las fichas
// de actividad en vivo.

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useEvents } from '../hooks/useEvents'
import { useDashboardStats } from '../hooks/useDashboard'
import { useModules } from '../hooks/useModules'
import Card from '../components/ui/card'
import { MessageFeed } from '../components/MessageFeed'
import { QUOTE_STATUS_LABELS } from '../lib/quoteStatus'

const CHIP_COLORS: Array<[string, string]> = [
  ['#e7eff0', '#31555c'],
  ['#e6efe9', '#1e6b4a'],
  ['#f3ead7', '#8a6d3b'],
  ['#f6e7e4', '#9c2f26'],
  ['#ece6f2', '#5b4a7e'],
  ['#e4e9f2', '#3c5687'],
  ['#f2e8dd', '#8a5a2b'],
  ['#e9e6dd', '#5b5643'],
]

function chipColor(key: string): [string, string] {
  let hash = 0
  for (const char of key) {
    hash = (hash + char.charCodeAt(0)) % CHIP_COLORS.length
  }
  return CHIP_COLORS[hash]
}

function StatCard({
  label,
  value,
  hint,
  tabular = true,
}: {
  label: string
  value: string
  hint?: string
  tabular?: boolean
}) {
  return (
    <Card className="p-5">
      <div className="plate-label">{label}</div>
      <div className={`mt-1.5 text-2xl font-bold tracking-tight text-ink ${tabular ? 'tabular' : ''}`}>
        {value}
      </div>
      {hint && <div className="tabular mt-1 text-xs text-linen-600">{hint}</div>}
    </Card>
  )
}

export default function DashboardPage() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const botName = user?.bot_name ?? 'Aura'

  const { events, status } = useEvents(token, () => {
    logout()
    navigate('/login')
  })

  const { data: stats, isLoading: statsLoading } = useDashboardStats()
  const { data: modules } = useModules()

  const dotClass =
    status === 'open' ? 'bg-ok' : status === 'connecting' ? 'bg-brass' : 'bg-linen-400'
  const statusLabel =
    status === 'open' ? 'En servicio' : status === 'connecting' ? 'Reconectando…' : 'Fuera de servicio'

  const topServices = (stats?.services ?? []).slice(0, 5)
  const maxInteractions = Math.max(1, ...topServices.map((service) => service.interactions))
  const activeServices =
    modules?.filter((module) => module.dev_status === 'active' && module.is_enabled).length ?? 0

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Panel de {botName}</h1>
          <p className="mt-1 text-sm text-linen-600">
            Su asistente atiende; estas son las notas del día.
          </p>
        </div>
        <div
          className="inline-flex h-9 items-center gap-2.5 rounded-full border border-linen-200 bg-panel px-4"
          title="Conexión en tiempo real con el asistente"
        >
          <span className={`h-2 w-2 rounded-full ${dotClass}`} />
          <span className="text-sm font-medium text-ink-soft">{statusLabel}</span>
        </div>
      </div>

      {/* Métricas del mostrador */}
      {statsLoading || !stats ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <Card key={index} className="p-5">
              <div className="skel h-3 w-24" />
              <div className="skel mt-3 h-7 w-16" />
              <div className="skel mt-2 h-3 w-20" />
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Clientes"
            value={String(stats.contacts.total)}
            hint={`${stats.contacts.active_last_7d} activos esta semana`}
          />
          <StatCard
            label="Cotizaciones"
            value={String(stats.quotes.total)}
            hint={`${stats.quotes.last_7d} esta semana`}
          />
          <StatCard
            label="Mensajes"
            value={String(stats.messages_last_7d)}
            hint="últimos 7 días"
          />
          <StatCard
            label="Servicios en línea"
            value={String(activeServices)}
            hint={`${stats.services.length - activeServices} en desarrollo`}
            tabular={false}
          />
        </div>
      )}

      {/* Servicios más demandados */}
      <section className="mt-8">
        <h2 className="plate-label mb-3">Servicios más demandados</h2>
        <Card className="p-5">
          {topServices.length === 0 ? (
            <p className="text-sm text-linen-600">Aún no hay servicios registrados.</p>
          ) : (
            <div className="space-y-3">
              {topServices.map((service) => {
                const [chipBg, chipInk] = chipColor(service.key)
                const widthPct = Math.round((service.interactions / maxInteractions) * 100)
                return (
                  <div key={service.key}>
                    <div className="flex items-baseline justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span
                          aria-hidden="true"
                          className="h-2 w-2 shrink-0 rounded-[2px]"
                          style={{ backgroundColor: chipBg }}
                        />
                        <span className="text-sm font-medium text-ink">{service.name}</span>
                        {service.dev_status === 'development' && (
                          <span className="rounded-full bg-linen-100 px-2 py-0.5 text-[0.65rem] font-medium text-linen-600">
                            En desarrollo
                          </span>
                        )}
                      </div>
                      <span className="tabular text-sm text-linen-600">
                        {service.interactions}
                        {service.interactions_7d > 0 && (
                          <span className="ml-1.5 text-xs text-brass-deep">
                            +{service.interactions_7d} esta semana
                          </span>
                        )}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-linen-100">
                      <div
                        className="h-full rounded-full bg-pine transition-[width] duration-300"
                        style={{ width: `${Math.max(widthPct, service.interactions > 0 ? 6 : 0)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </section>

      {/* Cotizaciones por estado (cuando hay) */}
      {stats && stats.quotes.total > 0 && (
        <section className="mt-8">
          <h2 className="plate-label mb-3">Cotizaciones por estado</h2>
          <Card className="flex flex-wrap gap-3 p-5">
            {Object.entries(stats.quotes.by_status).map(([key, count]) => (
              <div key={key} className="rounded-md bg-linen-50 px-4 py-2">
                <div className="plate-label">{QUOTE_STATUS_LABELS[key] ?? key}</div>
                <div className="tabular mt-0.5 text-lg font-semibold text-ink">{count}</div>
              </div>
            ))}
          </Card>
        </section>
      )}

      {/* Fichas de mensaje */}
      <section className="mt-8">
        <h2 className="plate-label mb-3">Fichas de mensaje</h2>
        <MessageFeed events={events} />
      </section>
    </div>
  )
}
