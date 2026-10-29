import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ServiciosPage from './pages/ServiciosPage'
import QuoterWorkspace from './pages/QuoterWorkspace'
import FollowUpPage from './pages/FollowUpPage'
import CatalogPage from './pages/CatalogPage'
import QuotesPage from './pages/QuotesPage'
import QuoteDetailPage from './pages/QuoteDetailPage'
import ClientesPage from './pages/ClientesPage'
import PagosPlanesPage from './pages/PagosPlanesPage'
import PlataformaPage from './pages/PlataformaPage'
import RemindersPage from './pages/RemindersPage'
import NegocioPage from './pages/NegocioPage'
import ServiceDataPage from './pages/ServiceDataPage'
import GoogleCallbackPage from './pages/GoogleCallbackPage'
import PlatformClientesPage from './pages/PlatformClientesPage'
import SetPasswordPage from './pages/SetPasswordPage'

// /crm siempre muestra el CRM del negocio (contactos y su ficha 360).
// La vista de "negocios de la plataforma" (tenants) vive en /admin.
function CrmPageRoute() {
  return <ClientesPage />
}

// Rutas viejas del cotizador → nuevas, conservando el sub-path
// (/servicios/quoter/cotizaciones/123 → /cotizador/cotizaciones/123)
function OldQuoterRedirect() {
  const { pathname } = useLocation()
  const rest = pathname.replace('/servicios/quoter', '')
  return <Navigate to={`/cotizador${rest}`} replace />
}

function PlatformOnlyRoute({ children }: { children: JSX.Element }) {
  const { user } = useAuth()
  return user?.is_platform_admin ? children : <Navigate to="/" replace />
}

function App() {
  const { user } = useAuth()

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/crear-contrasena" element={<SetPasswordPage />} />
        <Route path="/set-password" element={<Navigate to="/crear-contrasena" replace />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route element={<AppLayout />}>
        {/* Panel principal */}
        <Route path="/" element={<DashboardPage />} />

        {/* Cotizador: ahora accesible desde /cotizador */}
        <Route path="/cotizador" element={<QuoterWorkspace />}>
          <Route index element={<Navigate to="catalogo" replace />} />
          <Route path="catalogo" element={<CatalogPage />} />
          <Route path="cotizaciones" element={<QuotesPage />} />
          <Route path="cotizaciones/:id" element={<QuoteDetailPage />} />
          <Route path="seguimiento" element={<FollowUpPage />} />
        </Route>

        {/* CRM del negocio (contactos del dueño con ficha 360) — Mini CRM */}
        <Route path="/crm" element={<CrmPageRoute />} />

        {/* Recordatorios (sidebar: /agenda) */}
        <Route path="/agenda" element={<RemindersPage />} />

        {/* Servicios operativos (página parametrizada) */}
        <Route path="/inventario" element={<ServiceDataPage serviceKey="inventory" />} />
        <Route path="/mantenimiento" element={<ServiceDataPage serviceKey="maintenance" />} />
        <Route path="/garantias" element={<ServiceDataPage serviceKey="warranties" />} />
        <Route path="/finanzas" element={<ServiceDataPage serviceKey="expenses" />} />
        <Route path="/obra" element={<ServiceDataPage serviceKey="site-log" />} />

        {/* Mi Negocio */}
        <Route path="/negocio" element={<NegocioPage />} />

        {/* Google OAuth callback */}
        <Route path="/google/callback" element={<GoogleCallbackPage />} />

        {/* ── Superadmin ──────────────────────────────────────────────── */}
        <Route path="/clientes" element={<Navigate to="/crm" replace />} />
        <Route path="/clientes-bot" element={<PlatformClientesPage />} />
        <Route path="/admin" element={<Navigate to="/clientes-bot" replace />} />
        <Route path="/pagos" element={<PagosPlanesPage />} />
        <Route path="/plataforma" element={<PlatformOnlyRoute><PlataformaPage /></PlatformOnlyRoute>} />
        <Route path="/servicios" element={<ServiciosPage />} />

        {/* ── Redirecciones de compatibilidad (rutas antiguas → nuevas) ── */}
        <Route path="/servicios/quoter/*" element={<OldQuoterRedirect />} />
        <Route path="/servicios/reminders" element={<Navigate to="/agenda" replace />} />
        <Route path="/servicios/crm" element={<Navigate to="/crm" replace />} />
        <Route path="/modules" element={<Navigate to="/servicios" replace />} />
        <Route path="/catalog" element={<Navigate to="/cotizador/catalogo" replace />} />
        <Route path="/quotes" element={<Navigate to="/cotizador/cotizaciones" replace />} />
        <Route path="/conexion" element={<Navigate to="/plataforma" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
