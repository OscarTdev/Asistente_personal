import { Routes, Route, Navigate } from 'react-router-dom'
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

// /clientes por rol (adendo §3.2): superadmin ve sus negocios; dueño → su CRM
function ClientesPorRol() {
  const { user } = useAuth()
  if (user?.is_platform_admin) {
    return <PlatformClientesPage />
  }
  return <Navigate to="/servicios/crm" replace />
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
        <Route path="/" element={<DashboardPage />} />
        <Route path="/servicios" element={<ServiciosPage />} />
        <Route path="/servicios/quoter" element={<QuoterWorkspace />}>
          <Route index element={<Navigate to="catalogo" replace />} />
          <Route path="catalogo" element={<CatalogPage />} />
          <Route path="cotizaciones" element={<QuotesPage />} />
          <Route path="cotizaciones/:id" element={<QuoteDetailPage />} />
          <Route path="seguimiento" element={<FollowUpPage />} />
        </Route>
        <Route path="/servicios/reminders" element={<RemindersPage />} />
        <Route path="/servicios/crm" element={<ClientesPage />} />
        <Route path="/negocio" element={<NegocioPage />} />
        {/* Google OAuth: Google vuelve aquí con ?code=...&state=... */}
        <Route path="/google/callback" element={<GoogleCallbackPage />} />
        {/* Superadmin: sus secciones de plataforma (adendo §3.1) */}
        <Route path="/clientes" element={<ClientesPorRol />} />
        <Route path="/pagos" element={<PagosPlanesPage />} />
        <Route path="/plataforma" element={<PlataformaPage />} />
        {/* Admin completo de la plataforma: planes, chat, pagos, servicios */}
        <Route path="/admin" element={<AdminPage />} />
        {/* Rutas antiguas → nuevas, por memoria muscular */}
        <Route path="/agenda" element={<Navigate to="/servicios/reminders" replace />} />
        <Route path="/conexion" element={<Navigate to="/plataforma" replace />} />
        {/* Rutas antiguas → nuevas, por memoria muscular */}
        <Route path="/modules" element={<Navigate to="/servicios" replace />} />
        <Route path="/catalog" element={<Navigate to="/servicios/quoter/catalogo" replace />} />
        <Route path="/quotes" element={<Navigate to="/servicios/quoter/cotizaciones" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
