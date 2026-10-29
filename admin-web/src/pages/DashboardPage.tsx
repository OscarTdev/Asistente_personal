// DashboardPage v2 — Dark Premium.
// Panel de control principal: métricas, estado en tiempo real, actividad,
// accesos rápidos y onboarding guiado para primera vez.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useEvents } from '../hooks/useEvents'
import { useDashboardStats, useRealtimeActivity } from '../hooks/useDashboard'
import { useModules } from '../hooks/useModules'
import { MessageFeed } from '../components/MessageFeed'
import OnboardingTour, { useTourDone } from '../components/OnboardingTour'
import { QUOTE_STATUS_LABELS } from '../lib/quoteStatus'
import { ServiceStat } from '../types'
import {
  IconUsers,
  IconFileText,
  IconMessageCircle,
  IconZap,
  IconArrowRight,
  IconTrendingUp,
  IconActivity,
  IconShield,
  IconBuilding,
  IconCreditCard,
  IconWifi,
  IconSettings,
  IconCalendar,
  IconStar,
} from "@/components/ui/icons"

// ── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  iconColor,
  iconBg,
  trend,
}: {
  label: string
  value: string | number
  hint?: string
  icon: (props: React.SVGProps<SVGSVGElement>) => JSX.Element
  iconColor: string
  iconBg: string
  trend?: { value: number; label: string }
}) {
  return (
    <div className="stat-card animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
          style={{ background: iconBg }}
        >
          <Icon className="h-5 w-5" style={{ color: iconColor }} />
        </div>
        {trend && (
          <div
            className="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
            style={{
              background: trend.value >= 0 ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
              color: trend.value >= 0 ? 'var(--color-ok)' : 'var(--color-danger)',
            }}
          >
            <IconTrendingUp className="h-3 w-3" />
            {trend.value >= 0 ? '+' : ''}{trend.value}%
          </div>
        )}
      </div>
      <div className="mt-4">
        <div className="text-3xl font-bold tabular" style={{ color: 'var(--color-text-primary)', fontVariantNumeric: 'tabular-nums' }}>
          {value}
        </div>
        <div className="mt-1 text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          {label}
        </div>
        {hint && (
          <div className="mt-0.5 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            {hint}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Quick Action ──────────────────────────────────────────────────────────────
function QuickAction({
  icon: Icon,
  label,
  description,
  iconColor,
  iconBg,
  onClick,
}: {
  icon: (props: React.SVGProps<SVGSVGElement>) => JSX.Element
  label: string
  description: string
  iconColor: string
  iconBg: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="card card-interactive flex items-center gap-4 p-4 w-full text-left"
    >
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
        style={{ background: iconBg }}
      >
        <Icon className="h-5 w-5" style={{ color: iconColor }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          {label}
        </div>
        <div className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>
          {description}
        </div>
      </div>
      <IconArrowRight className="h-4 w-4 shrink-0" style={{ color: 'var(--color-text-disabled)' }} />
    </button>
  )
}

// ── Service Bar ───────────────────────────────────────────────────────────────
function ServiceBar({
  name,
  value,
  max,
  weeklyDelta,
}: {
  name: string
  value: number
  max: number
  weeklyDelta: number
}) {
  const pct = Math.round((value / Math.max(max, 1)) * 100)
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
          {name}
        </span>
        <div className="flex items-center gap-2">
          {weeklyDelta > 0 && (
            <span className="text-xs" style={{ color: 'var(--color-ok)' }}>
              +{weeklyDelta} esta semana
            </span>
          )}
          <span className="tabular text-sm font-semibold" style={{ color: 'var(--color-text-secondary)' }}>
            {value}
          </span>
        </div>
      </div>
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ transform: `scaleX(${Math.max(pct, value > 0 ? 4 : 0) / 100})` }}
        />
      </div>
    </div>
  )
}

// ── Superadmin Panel (solo cuando is_platform_admin) ─────────────────────────
function SuperadminQuickPanel() {
  const navigate = useNavigate()
  return (
    <section className="animate-fade-in" style={{ animationDelay: '240ms' }}>
      <div className="mb-4 flex items-center gap-2">
        <IconShield className="h-4 w-4" style={{ color: 'var(--color-accent-bright)' }} />
        <h2 className="text-sm font-semibold" style={{ color: 'var(--color-accent-bright)' }}>
          Panel de Plataforma
        </h2>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <QuickAction
          icon={IconBuilding}
          label="Negocios"
          description="Gestiona los negocios registrados"
          iconColor="#a78bfa"
          iconBg="rgba(124,58,237,0.12)"
          onClick={() => navigate('/admin')}
        />
        <QuickAction
          icon={IconCreditCard}
          label="Pagos y Planes"
          description="Precios, suscripciones, entitlements"
          iconColor="#34d399"
          iconBg="rgba(16,185,129,0.12)"
          onClick={() => navigate('/pagos')}
        />
        <QuickAction
          icon={IconWifi}
          label="Conexión WhatsApp"
          description="Estado y configuración del canal"
          iconColor="#60a5fa"
          iconBg="rgba(59,130,246,0.12)"
          onClick={() => navigate('/plataforma')}
        />
      </div>
    </section>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { user, token, logout } = useAuth()
  const navigate = useNavigate()
  const botName = user?.bot_name ?? 'Aura'
  const isAdmin = user?.is_platform_admin

  // Tour de primera vez
  const { done: tourDone, markDone: markTourDone } = useTourDone()
  const [showTour, setShowTour] = useState(!tourDone)

  const { events, status } = useEvents(token, () => {
    logout()
    navigate('/login')
  })

  const { data: stats, isLoading: statsLoading } = useDashboardStats()
  const { data: realtime } = useRealtimeActivity()
  const { data: modules } = useModules()

  const dotClass =
    status === 'open' ? 'ok' : status === 'connecting' ? 'warn' : 'offline'
  const statusLabel =
    status === 'open' ? 'En servicio' : status === 'connecting' ? 'Reconectando…' : 'Fuera de servicio'

  const topServices = (stats?.services ?? []).slice(0, 6)
  const maxInteractions = Math.max(1, ...topServices.map((s: ServiceStat) => s.interactions))
  const activeServices =
    modules?.filter((m) => m.dev_status === 'active' && m.is_enabled).length ?? 0

  const hourNow = new Date().getHours()
  const greeting =
    hourNow < 12 ? 'Buenos días' : hourNow < 18 ? 'Buenas tardes' : 'Buenas noches'

  return (
    <>
      {/* Tour de onboarding */}
      {showTour && (
        <OnboardingTour
          onClose={() => {
            markTourDone()
            setShowTour(false)
          }}
        />
      )}

      <div className="space-y-10">
        {/* ── Header ────────────────────────────────────────────────────── */}
        <div className="flex flex-wrap items-start justify-between gap-4 animate-fade-in">
          <div>
            <p className="text-sm font-medium mb-1" style={{ color: 'var(--color-text-tertiary)' }}>
              {greeting}, {user?.email?.split('@')[0] ?? 'Administrador'}
            </p>
            <h1 className="text-3xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
              Panel de{' '}
              <span
                style={{
                  background: 'linear-gradient(135deg, #a78bfa, #6366f1)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                {botName}
              </span>
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-text-tertiary)' }}>
              Tu asistente está atendiendo. Aquí el resumen del día.
            </p>
          </div>

          {/* Estado conexión */}
          <div className="flex items-center gap-4">
            <div
              className="flex items-center gap-2.5 rounded-full px-4 py-2"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
              }}
            >
              <span
                className={`status-dot ${dotClass} ${status === 'open' ? 'animate-pulse-dot' : ''}`}
              />
              <span className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                {statusLabel}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setShowTour(true)}
              className="btn btn-ghost btn-sm"
              title="Ver guía de inicio"
            >
              <IconStar className="h-4 w-4" />
              Guía
            </button>
          </div>
        </div>

        {/* ── Métricas ────────────────────────────────────────────────────── */}
        {statsLoading || !stats ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 stagger">
            {[0, 1, 2, 3].map((i: number) => (
              <div key={i} className="stat-card animate-fade-in">
                <div className="skel h-10 w-10 rounded-xl" />
                <div className="mt-4 skel h-8 w-20" />
                <div className="mt-2 skel h-3 w-28" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 stagger">
            <StatCard
              label="Clientes"
              value={stats.contacts.total}
              hint={`${stats.contacts.active_last_7d} activos esta semana`}
              icon={IconUsers}
              iconColor="#60a5fa"
              iconBg="rgba(59,130,246,0.12)"
              trend={{ value: stats.contacts.active_last_7d > 0 ? 12 : 0, label: '' }}
            />
            <StatCard
              label="Cotizaciones"
              value={stats.quotes.total}
              hint={`${stats.quotes.last_7d} esta semana`}
              icon={IconFileText}
              iconColor="#34d399"
              iconBg="rgba(16,185,129,0.12)"
            />
            <StatCard
              label="Mensajes (7d)"
              value={stats.messages_last_7d}
              icon={IconMessageCircle}
              iconColor="#f59e0b"
              iconBg="rgba(245,158,11,0.12)"
            />
            <StatCard
              label="Módulos activos"
              value={activeServices}
              hint={`de ${modules?.length ?? 0} disponibles`}
              icon={IconZap}
              iconColor="#a78bfa"
              iconBg="rgba(124,58,237,0.12)"
            />
          </div>
        )}

        {/* ── Superadmin panel ─────────────────────────────────────────────── */}
        {isAdmin && <SuperadminQuickPanel />}

        {/* ── Accesos rápidos (no superadmin) ──────────────────────────────── */}
        {!isAdmin && (
          <section className="animate-fade-in" style={{ animationDelay: '120ms' }}>
            <h2 className="mb-4 text-sm font-semibold" style={{ color: 'var(--color-text-tertiary)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Accesos rápidos
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <QuickAction
                icon={IconFileText}
                label="Cotizador"
                description="Catálogo, cotizaciones y seguimiento"
                iconColor="#34d399"
                iconBg="rgba(16,185,129,0.12)"
                onClick={() => navigate('/cotizador')}
              />
              <QuickAction
                icon={IconUsers}
                label="Clientes"
                description="CRM de contactos de WhatsApp"
                iconColor="#60a5fa"
                iconBg="rgba(59,130,246,0.12)"
                onClick={() => navigate('/clientes')}
              />
              <QuickAction
                icon={IconCalendar}
                label="Recordatorios"
                description="Agenda y alertas programadas"
                iconColor="#f59e0b"
                iconBg="rgba(245,158,11,0.12)"
                onClick={() => navigate('/agenda')}
              />
            </div>
          </section>
        )}

        {/* ── Servicios más demandados ─────────────────────────────────────── */}
        {isAdmin && topServices.length > 0 && (
          <section className="animate-fade-in" style={{ animationDelay: '180ms' }}>
            <div className="mb-4 flex items-center gap-2">
              <IconActivity className="h-4 w-4" style={{ color: 'var(--color-text-tertiary)' }} />
              <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
                Módulos más activos
              </h2>
            </div>
            <div
              className="card p-6"
            >
              <div className="space-y-4">
                {topServices.map((service: ServiceStat) => (
                  <ServiceBar
                    key={service.key}
                    name={service.name}
                    value={service.interactions}
                    max={maxInteractions}
                    weeklyDelta={service.interactions_7d}
                  />
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ── Cotizaciones por estado ──────────────────────────────────────── */}
        {stats && stats.quotes.total > 0 && (
          <section className="animate-fade-in" style={{ animationDelay: '240ms' }}>
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <IconFileText className="h-4 w-4" style={{ color: 'var(--color-text-tertiary)' }} />
                <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
                  Cotizaciones por estado
                </h2>
              </div>
              <button
                type="button"
                onClick={() => navigate('/cotizador')}
                className="btn btn-ghost btn-sm"
              >
                Ver todas
                <IconArrowRight className="h-3 w-3" />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Object.entries(stats.quotes.by_status).map(([key, count]) => {
                const colors: Record<string, { bg: string; text: string; border: string }> = {
                  draft:    { bg: 'rgba(245,158,11,0.08)',  text: '#f59e0b', border: 'rgba(245,158,11,0.2)' },
                  sent:     { bg: 'rgba(59,130,246,0.08)',  text: '#60a5fa', border: 'rgba(59,130,246,0.2)' },
                  accepted: { bg: 'rgba(16,185,129,0.08)', text: '#34d399', border: 'rgba(16,185,129,0.2)' },
                  rejected: { bg: 'rgba(239,68,68,0.08)',  text: '#f87171', border: 'rgba(239,68,68,0.2)'  },
                  expired:  { bg: 'rgba(120,113,108,0.08)',text: '#78716c', border: 'rgba(120,113,108,0.2)' },
                }
                const c = colors[key] ?? { bg: 'var(--color-bg-raised)', text: 'var(--color-text-secondary)', border: 'var(--color-border-subtle)' }
                return (
                  <div
                    key={key}
                    className="rounded-xl p-4"
                    style={{ background: c.bg, border: `1px solid ${c.border}` }}
                  >
                    <div className="text-xs font-semibold uppercase tracking-wider mb-1" style={{ color: c.text, opacity: 0.8 }}>
                      {QUOTE_STATUS_LABELS[key] ?? key}
                    </div>
                    <div className="text-2xl font-bold tabular" style={{ color: c.text }}>
                      {count}
                    </div>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* ── Actividad en tiempo real ─────────────────────────────────────── */}
        <section className="animate-fade-in" style={{ animationDelay: '300ms' }}>
          <div className="mb-4 flex items-center gap-2">
            <IconActivity className="h-4 w-4" style={{ color: 'var(--color-text-tertiary)' }} />
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
              Actividad en tiempo real
            </h2>
            <div
              className="ml-2 flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs"
              style={{
                background: status === 'open' ? 'rgba(16,185,129,0.1)' : 'rgba(255,255,255,0.04)',
                color: status === 'open' ? 'var(--color-ok)' : 'var(--color-text-tertiary)',
              }}
            >
              <span className={`status-dot ${dotClass}`} style={{ width: '5px', height: '5px' }} />
              Live
            </div>
          </div>
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wider text-linen-600">Usando Aura ahora</p>
            <p className="mt-1 text-2xl font-bold text-ink">
              {realtime?.active_now ?? 0}
            </p>
            <p className="text-xs text-linen-600">
              contactos activos en los últimos 15 minutos
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs uppercase tracking-wider text-linen-600">Interacciones recientes</p>
            <p className="mt-1 text-2xl font-bold text-ink">
              {realtime?.messages_in_window ?? 0}
            </p>
            <p className="text-xs text-linen-600">mensajes recibidos o respondidos</p>
          </div>
          </div>
          {(realtime?.users.length ?? 0) > 0 && (
          <div className="mb-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-linen-600">
              Quién está interactuando
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {realtime?.users.slice(0, 6).map((user) => (
                <div key={user.contact_id} className="flex items-center justify-between rounded-lg bg-black/10 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{user.name}</p>
                    <p className="text-xs text-linen-600">{user.wa_id}</p>
                  </div>
                  <span className="ml-3 shrink-0 text-xs text-linen-600">
                    {user.messages} msg{user.messages === 1 ? '' : 's'}
                  </span>
                </div>
              ))}
            </div>
          </div>
          )}
          <MessageFeed events={events} />
        </section>
      </div>
    </>
  )
}
