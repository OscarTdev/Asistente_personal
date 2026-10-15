// The concierge desk: bottle-green sidebar (the uniform) with a sliding
// brass rail marking the active section. On mobile the desk becomes a
// top bar with brass-underlined tabs.

import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { IconLogout, IconPanel, IconPerson, IconPower, IconReceipt, IconTag, IconWifi } from '../ui/icons'

interface NavItem {
  to: string
  label: string
  icon: (props: React.SVGProps<SVGSVGElement>) => JSX.Element
  end?: boolean
}

// Sidebar por rol (adendo §3.1 y §3.2): el dueño ve su asistente; el
// superadmin además ve su plataforma (Clientes, Pagos y planes, Plataforma).
const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Panel', icon: IconPanel, end: true },
  { to: '/servicios', label: 'Servicios', icon: IconPower },
  { to: '/negocio', label: 'Mi negocio', icon: IconPerson },
]

const PLATFORM_ITEMS: NavItem[] = [
  { to: '/clientes', label: 'Clientes', icon: IconTag },
  { to: '/pagos', label: 'Pagos y planes', icon: IconReceipt },
  { to: '/plataforma', label: 'Plataforma', icon: IconWifi },
]

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const botName = user?.bot_name ?? 'Aura'

  const items: NavItem[] = [...NAV_ITEMS]
  if (user?.is_platform_admin) {
    items.splice(1, 0, ...PLATFORM_ITEMS)
  }

  // The brass rail slides to the active section — the one authored motion.
  const itemRefs = useRef<Record<string, HTMLAnchorElement | null>>({})
  const [railTop, setRailTop] = useState<number | null>(null)

  useEffect(() => {
    const active = items.find((item) =>
      item.end ? location.pathname === '/' : location.pathname.startsWith(item.to)
    )
    const element = active ? itemRefs.current[active.to] : null
    if (element) {
      setRailTop(element.offsetTop)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-ground">
      {/* Desktop: the concierge's sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-pine md:flex">
        <div className="border-b border-white/10 px-5 py-5">
          <div className="text-lg font-bold tracking-[0.22em] text-ground">
            {botName.toUpperCase()}
          </div>
          <div className="mt-1 text-[0.6875rem] font-semibold uppercase tracking-[0.09em] text-linen-300">
            Panel de administración
          </div>
        </div>
        <nav className="relative flex-1 px-2 py-4">
          {railTop !== null && (
            <div
              aria-hidden="true"
              className="absolute left-0 w-[3px] rounded-r bg-brass transition-[top] duration-150 ease-out"
              style={{ top: railTop, height: 40 }}
            />
          )}
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              ref={(element) => {
                itemRefs.current[item.to] = element
              }}
              className={({ isActive }) =>
                `flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-white/10 text-brass-bright'
                    : 'text-ground/90 hover:bg-white/5 hover:text-ground'
                }`
              }
            >
              <item.icon className="h-5 w-5 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-white/10 px-5 py-4">
          <div className="truncate text-xs text-linen-300">{user?.email}</div>
          <button
            type="button"
            onClick={handleLogout}
            className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-lacre-tint hover:text-[#f0b3ac]"
          >
            <IconLogout className="h-4 w-4" />
            Cerrar sesión
          </button>
        </div>
      </aside>

      {/* Mobile: the desk becomes a top bar */}
      <div className="sticky top-0 z-30 md:hidden">
        <div className="flex h-14 items-center justify-between bg-pine px-4">
          <div className="text-base font-bold tracking-[0.22em] text-ground">
            {botName.toUpperCase()}
          </div>
          <button
            type="button"
            onClick={handleLogout}
            aria-label="Cerrar sesión"
            className="inline-flex h-11 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-lacre-tint hover:bg-white/5"
          >
            <IconLogout className="h-5 w-5" />
            Salir
          </button>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-b border-white/10 bg-pine px-2 pb-1">
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `inline-flex h-11 shrink-0 items-center border-b-2 px-3 text-sm font-medium transition-colors ${
                  isActive
                    ? 'border-brass text-brass-bright'
                    : 'border-transparent text-ground/90 hover:text-ground'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Content */}
      <main className="md:ml-60 md:px-10 md:py-8 px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
