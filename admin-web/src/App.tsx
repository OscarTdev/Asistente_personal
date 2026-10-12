import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ServiciosPage from './pages/ServiciosPage'
import QuoterWorkspace from './pages/QuoterWorkspace'
import CatalogPage from './pages/CatalogPage'
import QuotesPage from './pages/QuotesPage'
import QuoteDetailPage from './pages/QuoteDetailPage'
import ClientesPage from './pages/ClientesPage'

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
        </Route>
        <Route path="/clientes" element={<ClientesPage />} />
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
