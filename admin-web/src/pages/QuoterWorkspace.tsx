// Workspace del servicio Cotizador: el catálogo y las cotizaciones del
// asistente viven aquí, como pestañas del mismo mostrador.

import { Link, NavLink, Outlet } from 'react-router-dom'
import { IconArrowLeft } from '../components/ui/icons'

const tabs = [
  { to: '/servicios/quoter/catalogo', label: 'Catálogo de precios' },
  { to: '/servicios/quoter/cotizaciones', label: 'Cotizaciones' },
  { to: '/servicios/quoter/seguimiento', label: 'Seguimiento' },
]

export default function QuoterWorkspace() {
  return (
    <div>
      <Link
        to="/servicios"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-pine hover:underline"
      >
        <IconArrowLeft className="h-4 w-4" />
        Servicios
      </Link>

      <div className="mt-3">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Cotizador</h1>
        <p className="mt-1 text-sm text-linen-600">
          El técnico envía audio, foto o texto y el asistente cotiza desde su propio
          libro de precios.
        </p>
      </div>

      <nav className="mt-6 flex gap-1 border-b border-linen-200">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `inline-flex h-11 shrink-0 items-center border-b-2 px-4 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-brass text-brass-bright'
                  : 'border-transparent text-linen-600 hover:text-ink'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-6">
        <Outlet />
      </div>
    </div>
  )
}
