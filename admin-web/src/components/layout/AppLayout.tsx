// AppLayout v2 — Dark Premium.
// Sidebar reorganizado por secciones claras:
//   ASISTENTE: Panel, Cotizaciones, CRM, Recordatorios
//   MI NEGOCIO: Configuración
//   SUPERADMIN (solo is_platform_admin): Negocios, Pagos & Planes, Plataforma, Admin Completo

import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
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
  IconPanel,
  IconChevronDown,
  IconChevronRight,
  IconZap,
  IconBell,
} from '../ui/icons'

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

// ── Secciones del sidebar por rol ──────────────────────────────────────────
const OWNER_SECTIONS: NavSection[] = [
  {
    label: 'Asistente',
    items: [
      { to: '/', label: 'Panel', icon: IconGrid, end: true },
      { to: '/cotizador', label: 'Cotizador', icon: IconFileText },
      { to: '/clientes', label: 'Clientes', icon: IconUsers },
      { to: '/agenda', label: 'Recordatorios', icon: IconCalendar },
    ],
  },
  {
    label: 'Mi Negocio',
    items: [
      { to: '/negocio', label: 'Configuración', icon: IconSettings },
    ],
  },
]

const PLATFORM_SECTIONS: NavSection[] = [
  {
    label: 'Plataforma',
    items: [
      { to: '/admin', label: 'Negocios', icon: IconBuilding },
      { to: '/pagos', label: 'Pagos y planes', icon: IconCreditCard },
      { to: '/plataforma', label: 'Conexión WhatsApp', icon: IconWifi },
      { to: '/servicios', label: 'Módulos y permisos', icon: IconZap },
    ],
  },
]

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const botName = user?.bot_name ?? 'Aura'
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  const isAdmin = user?.is_platform_admin

  // Las secciones del owner siempre aparecen; las de plataforma solo para superadmin
  const sections: NavSection[] = isAdmin
    ? [...OWNER_SECTIONS, ...PLATFORM_SECTIONS]
    : OWNER_SECTIONS

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // Cierra el sidebar mobile al navegar
  useEffect(() => { setMobileSidebarOpen(false) }, [location.pathname])

  const initials = (user?.email ?? 'A')[0].toUpperCase()

  return (
    <div className="min-h-screen" style={{ background: 'var(--color-bg-base)', display: 'flex' }}>

      {/* ── Mobile overlay ────────────────────────────────────────────── */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* ── SIDEBAR ───────────────────────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-60 flex-col sidebar
          transition-transform duration-300 ease-in-out
          ${mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 md:flex`}
        style={{ display: 'flex' }}
      >
        {/* Logo / Bot name */}
        <div className="flex items-center gap-3 px-4 py-5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold"
            style={{
              background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
              color: '#fff',
              boxShadow: '0 0 12px rgba(124,58,237,0.4)',
            }}
          >
            {botName[0].toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
              {botName}
            </div>
            <div className="text-[10px] font-medium" style={{ color: 'var(--color-text-tertiary)', letterSpacing: '0.06em' }}>
              Panel de control
            </div>
          </div>
        </div>

        {/* Superadmin badge */}
        {isAdmin && (
          <div className="px-3 pt-3">
            <div className="superadmin-banner">
              <IconShield className="h-3.5 w-3.5 shrink-0" />
              Super Admin
            </div>
          </div>
        )}

        {/* Navegación por secciones */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {sections.map((section, si) => (
            <div key={section.label}>
              {(si > 0 || isAdmin) && (
                <div className="nav-section-label">{section.label}</div>
              )}
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `nav-item mb-0.5 ${isActive ? 'active' : ''}`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.badge && (
                    <span
                      className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                      style={{ background: 'var(--color-accent-wash)', color: 'var(--color-accent-bright)' }}
                    >
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {/* Footer del sidebar: usuario + cerrar sesión */}
        <div
          className="px-3 py-4"
          style={{ borderTop: '1px solid var(--color-border-subtle)' }}
        >
          <div
            className="flex items-center gap-3 rounded-lg px-2 py-2 mb-2"
            style={{ background: 'var(--color-bg-raised)' }}
          >
            <div
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-accent-wash)', color: 'var(--color-accent-bright)', border: '1px solid var(--color-accent-border)' }}
            >
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs font-medium" style={{ color: 'var(--color-text-primary)' }}>
                {user?.email}
              </div>
              <div className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                {isAdmin ? 'Super Admin' : user?.role === 'admin' ? 'Administrador' : 'Usuario'}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="nav-item w-full text-left"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            <IconLogout className="h-4 w-4" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* ── TOPBAR MÓVIL ──────────────────────────────────────────────── */}
      <div
        className="fixed top-0 left-0 right-0 z-30 flex h-14 items-center justify-between px-4 md:hidden"
        style={{ background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        <button
          type="button"
          onClick={() => setMobileSidebarOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ background: 'var(--color-bg-raised)', color: 'var(--color-text-secondary)' }}
          aria-label="Abrir menú"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
            <path fillRule="evenodd" d="M3 5h14a1 1 0 0 1 0 2H3a1 1 0 0 1 0-2Zm0 4h14a1 1 0 0 1 0 2H3a1 1 0 0 1 0-2Zm0 4h14a1 1 0 0 1 0 2H3a1 1 0 0 1 0-2Z" clipRule="evenodd" />
          </svg>
        </button>
        <div
          className="text-sm font-bold tracking-wide"
          style={{
            background: 'linear-gradient(135deg, #a78bfa, #6366f1)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          {botName}
        </div>
        <div
          className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold"
          style={{ background: 'var(--color-accent-wash)', color: 'var(--color-accent-bright)' }}
        >
          {initials}
        </div>
      </div>

      {/* ── CONTENIDO PRINCIPAL ───────────────────────────────────────── */}
      <main
        className="flex-1 min-h-screen"
        style={{
          marginLeft: '240px',
          paddingTop: '0',
          paddingBottom: '32px',
        }}
      >
        {/* Topbar desktop */}
        <div
          className="hidden md:flex sticky top-0 z-20 h-14 items-center justify-between px-8"
          style={{ background: 'rgba(10,10,15,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid var(--color-border-subtle)' }}
        >
          <div /> {/* espacio para breadcrumb futuro */}
          <div className="flex items-center gap-3">
            {isAdmin && (
              <div
                className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold"
                style={{ background: 'var(--color-accent-wash)', color: 'var(--color-accent-bright)', border: '1px solid var(--color-accent-border)' }}
              >
                <IconShield className="h-3 w-3" />
                Super Admin
              </div>
            )}
            <div
              className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-accent-wash)', color: 'var(--color-accent-bright)', border: '1px solid var(--color-accent-border)' }}
            >
              {initials}
            </div>
          </div>
        </div>

        <div className="px-6 py-8 md:px-10" style={{ marginTop: '0' }}>
          <Outlet />
        </div>
      </main>
    </div>
  )
}
