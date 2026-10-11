import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'

export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}