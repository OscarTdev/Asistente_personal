// AppLayout v3 — smb-admin shell (tinted L-frame + white sheet)
// design-taste-frontend direction sheet: frame tinted, sheet inset 8px, 16px radius, 1px edge

import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ErrorBoundary } from '../ErrorBoundary'
import { useAuth } from '../../auth/AuthContext'
import {
  IconGrid,
  IconFileText,
  IconUsers,
  IconCalendar,
  IconSettings,
  IconLogout,
  IconShield,
  IconBuilding,
  IconCreditCard,
  IconWifi,
  IconZap,
  IconPanel,
  IconSearch,
  IconChevronLeft,
  IconSun,
  IconMoon,
  IconAuto,
} from '../ui/icons'
import { cn } from '../../lib/utils'

interface NavItem {
  to: string
  label: string
  icon: (props: React.SVGProps<SVGSVGElement>) => JSX.Element
  end?: boolean
  badge?: string
}

interface NavSection {
  label: string
  items: NavItem[]
}

const OWNER_SECTIONS: NavSection[] = [
  {
    label: 'Operación',
    items: [
      { to: '/', label: 'Inicio', icon: IconGrid, end: true },
      { to: '/cotizador', label: 'Cotizador', icon: IconFileText },
      { to: '/crm', label: 'Mini CRM · mis clientes', icon: IconUsers },
      { to: '/agenda', label: 'Recordatorios', icon: IconCalendar },
    ],
  },
  {
    label: 'Configuración del negocio',
    items: [
      { to: '/negocio', label: 'Configuración', icon: IconSettings },
      { to: '/servicios', label: 'Mis servicios', icon: IconZap },
      { to: '/pagos', label: 'Mi plan', icon: IconCreditCard },
    ],
  },
]

const PLATFORM_SECTIONS: NavSection[] = [
  {
    label: 'Administración de plataforma',
    items: [
      { to: '/clientes-bot', label: 'Dueños del bot', icon: IconBuilding },
      { to: '/plataforma', label: 'Conexión WhatsApp', icon: IconWifi },
    ],
  },
]

export default function AppLayout() {
  const { user, logout, stopImpersonating, isImpersonating, theme, setTheme, resolvedTheme } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const botName = user?.bot_name ?? 'Aura'
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  const isAdmin = user?.is_platform_admin
  const sections: NavSection[] = isAdmin ? [...OWNER_SECTIONS, ...PLATFORM_SECTIONS] : OWNER_SECTIONS
  const initials = (user?.email ?? 'A')[0].toUpperCase()

  const handleLogout = () => { logout(); navigate('/login') }
  useEffect(() => { setMobileSidebarOpen(false); setMobileSearchOpen(false) }, [location.pathname])

  const cycleTheme = () => {
    const order: ('light' | 'dark' | 'system')[] = ['light', 'dark', 'system']
    const current = order.indexOf(theme)
    const next = order[(current + 1) % order.length]
    setTheme(next)
  }

  const themeLabels: Record<'light' | 'dark' | 'system', string> = {
    light: 'Claro',
    dark: 'Oscuro',
    system: 'Sistema',
  }

  const themeIcons = {
    light: <IconSun className="h-4 w-4" />,
    dark: <IconMoon className="h-4 w-4" />,
    system: <IconAuto className="h-4 w-4" />,
  }

  return (
    <div className="app-shell" style={{ minHeight: '100vh' }}>

      {/* ── Mobile overlay ────────────────────────────────────────────── */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)' }}
          onClick={() => setMobileSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── SIDEBAR (tinted frame ground) ──────────────────────────────── */}
      <aside
        className={cn(
          'app-sidebar fixed inset-y-0 left-0 z-50 w-65 flex flex-col transition-transform duration-200 ease-out',
          'md:translate-x-0',
          mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        style={{ display: 'flex' }}
        aria-label="Navegación principal"
      >
        {/* Logo / Bot name */}
        <div className="flex items-center gap-3 px-4 py-5 border-b" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold"
            style={{
              background: 'linear-gradient(135deg, var(--color-brand-magenta), var(--color-brand-rose))',
              color: '#fff',
              boxShadow: '0 0 12px var(--color-brand-magenta-border)',
            }}
            aria-hidden="true"
          >
            {botName[0].toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
              {botName}
            </div>
            <div className="text-[10px] font-medium tracking-wider" style={{ color: 'var(--color-ink-muted)' }}>
              Panel de control
            </div>
          </div>
        </div>

        {/* Superadmin badge */}
        {isAdmin && (
          <div className="px-3 pt-3">
            <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wider"
              style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}>
              <IconShield className="h-3 w-3 shrink-0" aria-hidden="true" />
              Super Admin
            </div>
          </div>
        )}

        {/* Navegación (aria-current lo pone NavLink solo en la activa) */}
        <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Secciones">
          {sections.map((section, si) => (
            <div key={section.label}>
              {(si > 0 || isAdmin) && (
                <div className="text-[10px] font-bold tracking-widest uppercase px-3 mb-2" style={{ color: 'var(--color-ink-muted)', letterSpacing: '0.12em' }}>
                  {section.label}
                </div>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className="nav-item mb-0.5 flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors duration-150"
                >
                  <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.badge && (
                    <span className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                      style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)' }}>
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer: user + logout */}
        <div className="px-3 py-4 border-t" style={{ borderColor: 'var(--color-border-subtle)' }}>
          <div className="flex items-center gap-3 rounded-lg px-2 py-2 mb-2" style={{ background: 'var(--color-raised)' }}>
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}>
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium" style={{ color: 'var(--color-ink)' }}>
                {user?.email}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-ink-muted)' }}>
                {isAdmin ? 'Super Admin' : user?.role === 'admin' ? 'Administrador' : 'Usuario'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="nav-item w-full text-left"
            style={{ color: 'var(--color-ink-muted)' }}
          >
            <IconLogout className="h-4 w-4" aria-hidden="true" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* ── TOPBAR (tinted frame ground, 48px) ─────────────────────────── */}
      <header className="app-topbar hidden md:flex h-12 items-center justify-between px-6 border-b sticky top-0 z-10"
        style={{ background: 'var(--color-ground)', borderColor: 'var(--color-border-subtle)' }}
        role="banner"
      >
        {/* Breadcrumb / page title area */}
        <div className="flex-1 min-w-0" aria-hidden="true" />

        {/* Centered search — real: Enter lleva al CRM con la consulta */}
        <div className="topbar-search flex-1 max-w-79 mx-auto" role="search">
          <label htmlFor="global-search" className="sr-only">Buscar clientes</label>
          <div className="relative">
            <IconSearch className="topbar-search-icon h-4 w-4" aria-hidden="true" />
            <input
              id="global-search"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  navigate(`/crm?search=${encodeURIComponent(searchQuery.trim())}`)
                  setMobileSearchOpen(false)
                }
              }}
              placeholder="Buscar clientes — Enter para ir al CRM…"
              className="topbar-search-input w-full h-9 pl-10 pr-4 text-sm rounded-full"
              aria-label="Buscar clientes"
            />
          </div>
        </div>

        {/* Right: theme toggle + user avatar */}
        <div className="flex items-center gap-3 ml-auto">
          <button
            type="button"
            onClick={cycleTheme}
            className="flex h-9 w-9 items-center justify-center rounded-lg transition-colors"
            style={{ background: 'var(--color-bg-raised)', color: 'var(--color-text-secondary)' }}
            title={`Tema: ${themeLabels[theme]} (clic para cambiar)`}
            aria-label={`Cambiar tema, actual: ${themeLabels[theme]}`}
          >
            {themeIcons[theme]}
          </button>
          {isAdmin && (
            <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-wider"
              style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}>
              <IconShield className="h-3 w-3" aria-hidden="true" />
              Super Admin
            </div>
          )}
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold"
            style={{ background: 'var(--color-brand-magenta-wash)', color: 'var(--color-brand-magenta)', border: '1px solid var(--color-brand-magenta-border)' }}
            aria-label={`Usuario: ${user?.email}`}
          >
            {initials}
          </div>
        </div>
      </header>

      {/* ── Mobile topbar ─────────────────────────────────────────────── */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-30 flex h-12 items-center justify-between px-4 border-b"
        style={{ background: 'var(--color-ground)', borderColor: 'var(--color-border-subtle)' }}
        role="banner"
      >
        <button
          type="button"
          onClick={() => setMobileSidebarOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ background: 'var(--color-raised)', color: 'var(--color-ink-soft)' }}
          aria-label="Abrir menú"
          aria-expanded={mobileSidebarOpen}
        >
          <IconChevronLeft className="h-5 w-5" aria-hidden="true" />
        </button>
        <div className="flex-1 text-center text-sm font-semibold truncate" style={{ color: 'var(--color-ink)' }}>
          {botName}
        </div>
        <button
          type="button"
          onClick={() => setMobileSearchOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ background: 'var(--color-raised)', color: 'var(--color-ink-soft)' }}
          aria-label="Buscar"
          aria-expanded={mobileSearchOpen}
        >
          <IconSearch className="h-5 w-5" aria-hidden="true" />
        </button>
      </header>

      {/* ── Mobile search sheet ───────────────────────────────────────── */}
      {mobileSearchOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex flex-col"
          style={{ background: 'var(--color-ground)' }}
          role="dialog"
          aria-modal="true"
          aria-label="Buscar"
        >
          <div className="flex h-12 items-center justify-between px-4 border-b" style={{ borderColor: 'var(--color-border-subtle)' }}>
            <label htmlFor="mobile-search" className="sr-only">Buscar clientes</label>
            <div className="flex-1 relative">
              <IconSearch className="topbar-search-icon h-4 w-4" aria-hidden="true" />
              <input
                id="mobile-search"
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    navigate(`/crm?search=${encodeURIComponent(searchQuery.trim())}`)
                    setMobileSearchOpen(false)
                  }
                }}
                placeholder="Buscar clientes — Enter para ir al CRM…"
                className="topbar-search-input w-full h-9 pl-10 pr-4 text-sm rounded-full"
                autoFocus
              />
            </div>
            <button
              type="button"
              onClick={() => setMobileSearchOpen(false)}
              className="flex h-9 w-9 items-center justify-center rounded-lg ml-2"
              style={{ background: 'var(--color-raised)', color: 'var(--color-ink-soft)' }}
              aria-label="Cerrar búsqueda"
            >
              <IconChevronLeft className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-sm" style={{ color: 'var(--color-ink-muted)' }}>
              Pulsa Enter para ver los clientes que coinciden en el CRM.
            </p>
          </div>
        </div>
      )}

      {/* ── WHITE SHEET CONTENT (inset 8px, 16px radius, 1px edge) ─────── */}
      <main className="app-content" role="main" style={{ minHeight: 'calc(100vh - 48px)' }}>
        <div className="app-content-inner">
          {/* Banner de impersonación si el superadmin está viendo el panel de un cliente */}
          {isImpersonating && (
            <div
              className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl mb-5 text-xs font-medium animate-fade-in shadow-sm"
              style={{
                background: 'linear-gradient(90deg, rgba(236,72,153,0.12), rgba(168,85,247,0.12))',
                border: '1px solid var(--color-brand-magenta-border)',
                color: 'var(--color-ink)',
              }}
            >
              <div className="flex items-center gap-2.5">
                <span className="flex h-2.5 w-2.5 rounded-full bg-pink-500 animate-pulse" />
                <span>
                  Modo Vista Cliente: Estás explorando el panel de{' '}
                  <strong className="font-semibold text-pink-600 dark:text-pink-400">
                    {user?.tenant_name || user?.full_name || 'Cliente'}
                  </strong>
                  {user?.plan && (
                    <span className="ml-1.5 rounded-full px-2 py-0.5 text-[10px] uppercase font-bold bg-pink-500/10 text-pink-500">
                      Plan {user.plan}
                    </span>
                  )}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  stopImpersonating()
                  navigate('/clientes')
                }}
                className="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-semibold shadow-sm transition-all hover:opacity-90"
                style={{
                  background: 'var(--color-brand-magenta)',
                  color: '#fff',
                }}
              >
                Volver a Super Admin ✕
              </button>
            </div>
          )}

          {/* Crash de página → errata de lacre dentro del panel, no pantalla blanca */}
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  )
}