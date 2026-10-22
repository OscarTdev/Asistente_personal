// OnboardingTour — guía interactiva para la primera visita al panel.
// Se muestra si localStorage('aura_tour_done') no está seteado.
// 5 pasos con ilustración, descripción y progreso visual.

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  IconGrid,
  IconFileText,
  IconUsers,
  IconSettings,
  IconShield,
  IconZap,
  IconArrowRight,
  IconX,
  IconCheck,
} from './ui/icons'

const TOUR_KEY = 'aura_tour_done_v2'

interface TourStep {
  icon: (props: React.SVGProps<SVGSVGElement>) => JSX.Element
  iconColor: string
  iconBg: string
  title: string
  description: string
  action?: { label: string; to: string }
}

const OWNER_STEPS: TourStep[] = [
  {
    icon: IconGrid,
    iconColor: '#a78bfa',
    iconBg: 'rgba(124,58,237,0.15)',
    title: 'Bienvenido a tu panel de control',
    description: 'Desde aquí controlas todo tu asistente de WhatsApp. Verás métricas en tiempo real, actividad reciente y el estado de tu conexión.',
  },
  {
    icon: IconFileText,
    iconColor: '#34d399',
    iconBg: 'rgba(16,185,129,0.12)',
    title: 'Cotizador con IA',
    description: 'Tu asistente genera cotizaciones automáticamente desde WhatsApp. En el Cotizador puedes gestionar el catálogo de precios, ver las cotizaciones enviadas y hacer seguimiento.',
    action: { label: 'Ver cotizador', to: '/cotizador' },
  },
  {
    icon: IconUsers,
    iconColor: '#60a5fa',
    iconBg: 'rgba(59,130,246,0.12)',
    title: 'CRM de Clientes',
    description: 'Todos tus clientes de WhatsApp en un solo lugar. Busca contactos, ve el historial de conversaciones y lleva notas de cada cliente.',
    action: { label: 'Ver clientes', to: '/clientes' },
  },
  {
    icon: IconSettings,
    iconColor: '#f59e0b',
    iconBg: 'rgba(245,158,11,0.12)',
    title: 'Configura tu negocio',
    description: 'Sube el logo de tu empresa (aparecerá en los PDFs), conecta Google Workspace para gestionar tu correo y calendario, y personaliza el nombre de tu asistente.',
    action: { label: 'Mi negocio', to: '/negocio' },
  },
  {
    icon: IconZap,
    iconColor: '#c084fc',
    iconBg: 'rgba(192,132,252,0.12)',
    title: '¡Todo listo!',
    description: 'Tu asistente Aura está listo para atender clientes. Envía un mensaje de WhatsApp al número configurado para ver la magia en acción.',
  },
]

const ADMIN_STEP: TourStep = {
  icon: IconShield,
  iconColor: '#a78bfa',
  iconBg: 'rgba(124,58,237,0.15)',
  title: 'Modo Super Admin',
  description: 'Tienes acceso completo a la plataforma: gestiona los negocios registrados, configura los planes y precios, administra módulos y monitorea las conexiones de WhatsApp.',
  action: { label: 'Ver negocios', to: '/admin' },
}

export function useTourDone() {
  const [done, setDone] = useState(() => Boolean(localStorage.getItem(TOUR_KEY)))
  const markDone = () => {
    localStorage.setItem(TOUR_KEY, '1')
    setDone(true)
  }
  return { done, markDone }
}

export default function OnboardingTour({ onClose }: { onClose: () => void }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const isAdmin = user?.is_platform_admin
  const steps: TourStep[] = isAdmin
    ? [ADMIN_STEP, ...OWNER_STEPS.slice(1)]
    : OWNER_STEPS
  const [step, setStep] = useState(0)
  const current = steps[step]
  const isLast = step === steps.length - 1

  const handleNext = () => {
    if (isLast) {
      onClose()
    } else {
      setStep((s) => s + 1)
    }
  }

  const handleAction = () => {
    if (current.action) {
      navigate(current.action.to)
      onClose()
    }
  }

  return (
    <div className="tour-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="tour-card">
        {/* Cerrar */}
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center rounded-lg transition-colors"
          style={{ color: 'var(--color-text-tertiary)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          aria-label="Cerrar"
        >
          <IconX className="h-4 w-4" />
        </button>

        {/* Progreso */}
        <div className="mb-6 flex gap-1.5">
          {steps.map((_, i) => (
            <div
              key={i}
              className="h-1 flex-1 rounded-full transition-all duration-300"
              style={{
                background: i <= step ? 'var(--color-accent)' : 'var(--color-bg-raised)',
              }}
            />
          ))}
        </div>

        {/* Ícono */}
        <div
          className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl"
          style={{ background: current.iconBg }}
        >
          <current.icon className="h-7 w-7" style={{ color: current.iconColor }} />
        </div>

        {/* Texto */}
        <h2 className="mb-3 text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          {current.title}
        </h2>
        <p className="mb-6 leading-relaxed" style={{ color: 'var(--color-text-secondary)', fontSize: '0.9375rem' }}>
          {current.description}
        </p>

        {/* Acciones */}
        <div className="flex items-center gap-3">
          {current.action && (
            <button
              type="button"
              onClick={handleAction}
              className="btn btn-secondary btn-md"
            >
              {current.action.label}
              <IconArrowRight className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            onClick={handleNext}
            className="btn btn-primary btn-md ml-auto"
          >
            {isLast ? (
              <>
                <IconCheck className="h-4 w-4" />
                Empezar
              </>
            ) : (
              <>
                Siguiente
                <IconArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </div>

        {/* Paso X de N */}
        <div className="mt-4 text-center text-xs" style={{ color: 'var(--color-text-disabled)' }}>
          Paso {step + 1} de {steps.length}
        </div>
      </div>
    </div>
  )
}
