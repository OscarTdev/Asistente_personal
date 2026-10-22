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
import PlatformClientesPage from './pages/PlatformClientesPage'
import PagosPlanesPage from './pages/PagosPlanesPage'
import PlataformaPage from './pages/PlataformaPage'
import RemindersPage from './pages/RemindersPage'
import NegocioPage from './pages/NegocioPage'
import GoogleCallbackPage from './pages/GoogleCallbackPage'
import AdminPage from './pages/AdminPage'

// /clientes por rol: superadmin ve sus negocios; dueño → su CRM
function ClientesPorRol() {
  const { user } = useAuth()
  if (user?.is_platform_admin) {
    return <PlatformClientesPage />
  }
  return <ClientesPage />
}

// Rutas viejas del cotizador → nuevas, conservando el sub-path
// (/servicios/quoter/cotizaciones/123 → /cotizador/cotizaciones/123)
function OldQuoterRedirect() {
  const { pathname } = useLocation()
  const rest = pathname.replace('/servicios/quoter', '')
  return <Navigate to={`/cotizador${rest}`} replace />
}

function App() {
  const { user } = useAuth()

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
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

        {/* Clientes / CRM (rol dependiente) */}
        <Route path="/clientes" element={<ClientesPorRol />} />

        {/* Recordatorios (sidebar: /agenda) */}
        <Route path="/agenda" element={<RemindersPage />} />

        {/* Mi Negocio */}
        <Route path="/negocio" element={<NegocioPage />} />

        {/* Google OAuth callback */}
        <Route path="/google/callback" element={<GoogleCallbackPage />} />

        {/* ── Superadmin ──────────────────────────────────────────────── */}
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/pagos" element={<PagosPlanesPage />} />
        <Route path="/plataforma" element={<PlataformaPage />} />
        <Route path="/servicios" element={<ServiciosPage />} />

        {/* ── Redirecciones de compatibilidad (rutas antiguas → nuevas) ── */}
        <Route path="/servicios/quoter/*" element={<OldQuoterRedirect />} />
        <Route path="/servicios/reminders" element={<Navigate to="/agenda" replace />} />
        <Route path="/servicios/crm" element={<Navigate to="/clientes" replace />} />
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
