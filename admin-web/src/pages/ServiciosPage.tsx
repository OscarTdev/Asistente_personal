// Servicios del asistente (admin): cada carta es un servicio, construido
// ("active") o planeado ("development"), con su interruptor y su entrada.

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import Card from '../components/ui/card'
import Switch from '../components/ui/switch'
import Button from '../components/ui/button'
import ErrorSlip from '../components/ui/error-slip'
import { IconEnter } from '../components/ui/icons'
import { useModules, useToggleModule } from '../hooks/useModules'
import { Module } from '../types'

// Stationery ink chips — muted tints, one per service identity
const CHIP_COLORS: Array<[string, string]> = [
  ['#e7eff0', '#31555c'],
  ['#e6efe9', '#1e6b4a'],
  ['#f3ead7', '#8a6d3b'],
  ['#f6e7e4', '#9c2f26'],
  ['#ece6f2', '#5b4a7e'],
  ['#e4e9f2', '#3c5687'],
  ['#f2e8dd', '#8a5a2b'],
  ['#e9e6dd', '#5b5643'],
]

function chipColor(key: string): [string, string] {
  let hash = 0
  for (const char of key) {
    hash = (hash + char.charCodeAt(0)) % CHIP_COLORS.length
  }
  return CHIP_COLORS[hash]
}

function ServiceCard({
  module,
  toggling,
  onToggle,
  onEnter,
}: {
  module: Module
  toggling: boolean
  onToggle: (module: Module, value: boolean) => void
  onEnter: (module: Module) => void
}) {
  const [chipBg] = chipColor(module.key)
  const inDevelopment = module.dev_status === 'development'

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
              style={{ backgroundColor: chipBg }}
            />
            <h3 className="truncate text-base font-semibold text-ink">{module.name}</h3>
          </div>
          <div className="plate-label mt-1.5">
            {module.category}
            {module.is_custom ? ' · personalizado' : ''}
          </div>
        </div>
        <Switch
          checked={module.is_enabled}
          disabled={inDevelopment || toggling}
          onChange={(value) => onToggle(module, value)}
          label={`Encender o apagar ${module.name}`}
        />
      </div>
      <p className="mt-3 min-h-[2.5rem] text-sm text-ink-soft">{module.description}</p>
      <div className="mt-4 flex items-center justify-between">
        {inDevelopment ? (
          <span className="rounded-full bg-linen-100 px-2 py-1 text-xs font-medium text-linen-600">
            En desarrollo
          </span>
        ) : module.is_enabled ? (
          <span className="rounded-full bg-ok-wash px-2 py-1 text-xs font-medium text-ok">
            En servicio
          </span>
        ) : (
          <span className="rounded-full bg-linen-100 px-2 py-1 text-xs font-medium text-linen-600">
            Apagado
          </span>
        )}
        {module.dev_status === 'active' && module.is_enabled && module.workspace && (
          <Button type="button" variant="outline" size="sm" onClick={() => onEnter(module)}>
            <IconEnter className="h-4 w-4" />
            Entrar
          </Button>
        )}
      </div>
    </Card>
  )
}

export default function ServiciosPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const navigate = useNavigate()
  const { data: modules, isLoading, error } = useModules()
  const toggleModule = useToggleModule()
  const [togglingKey, setTogglingKey] = useState<string | null>(null)
  // The concierge notes the change; the card stays marked until seen.
  const [heldKey, setHeldKey] = useState<string | null>(null)

  if (!isAdmin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">Solo los administradores gestionan los servicios del asistente.</p>
      </div>
    )
  }

  const handleToggle = (module: Module, isEnabled: boolean) => {
    setTogglingKey(module.key)
    toggleModule.mutate(
      { moduleKey: module.key, isEnabled },
      {
        onSuccess: () => setHeldKey(module.key),
        onSettled: () => setTogglingKey(null),
      }
    )
  }

  const handleEnter = (module: Module) => {
    if (module.workspace) {
      navigate(module.workspace)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Servicios</h1>
        <p className="mt-1 text-sm text-linen-600">
          Las habilidades del asistente, una por carta. Encienda las que estén listas;
          las demás se encienden cuando toque perfeccionarlas.
        </p>
      </div>

      <div className="mb-4">
        <ErrorSlip message={error?.message ?? toggleModule.error?.message ?? null} />
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <div key={index} className="ficha p-5">
              <div className="skel h-5 w-2/3" />
              <div className="skel mt-3 h-3 w-1/3" />
              <div className="skel mt-4 h-10 w-full" />
            </div>
          ))}
        </div>
      )}

      {modules && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => (
            <div
              key={module.key}
              className={`rounded-lg ${heldKey === module.key ? 'row-hold' : ''}`}
              onMouseEnter={() => {
                if (heldKey === module.key) {
                  setHeldKey(null)
                }
              }}
              onFocus={() => {
                if (heldKey === module.key) {
                  setHeldKey(null)
                }
              }}
            >
              <ServiceCard
                module={module}
                toggling={togglingKey === module.key}
                onToggle={handleToggle}
                onEnter={handleEnter}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
