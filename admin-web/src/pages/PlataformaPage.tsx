// Plataforma (superadmin, adendo §3.1): el número de WhatsApp compartido
// por todos los negocios, los proveedores de IA y (en fases próximas) la
// auditoría de la plataforma.

import { useState } from 'react'
import { Card } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { Input } from "../components/ui/input"
import { ErrorSlip } from "../components/ui/error-slip"
import { IconPower, IconWifi, IconBrain, IconRefreshCw, IconKey } from "@/components/ui/icons"
import { useAuth } from '../auth/AuthContext'
import {
  useConnectWhatsapp,
  useDisconnectWhatsapp,
  useTestSendWhatsapp,
  useWhatsappStatus,
} from '../hooks/useWhatsapp'
import {
  usePlatformAIConfig,
  useUpdatePlatformAIConfig,
} from '../hooks/usePlatformAI'

function stateLabel(state: string): string {
  switch (state) {
    case 'open':
      return 'En línea'
    case 'connecting':
      return 'Esperando escaneo'
    case 'close':
      return 'Desconectado'
    case 'offline':
      return 'API fuera de línea'
    default:
      return state
  }
}

function stateDot(state: string): string {
  if (state === 'open') return 'bg-ok'
  if (state === 'connecting') return 'bg-brass'
  return 'bg-linen-400'
}

export default function PlataformaPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const isPlatformAdmin = user?.is_platform_admin
  const { data: status } = useWhatsappStatus()
  const connect = useConnectWhatsapp()
  const disconnect = useDisconnectWhatsapp()
  const testSend = useTestSendWhatsapp()
  const { data: aiConfig, isLoading: aiLoading, error: aiError } = usePlatformAIConfig()
  const updateAI = useUpdatePlatformAIConfig()

  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [pairingCode, setPairingCode] = useState<string | null>(null)
  const [testNumber, setTestNumber] = useState('')
  const [testText, setTestText] = useState('¡Hola! Soy el asistente Aura en pruebas 🛠')
  const [testResult, setTestResult] = useState<string | null>(null)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  if (!isPlatformAdmin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">
          Solo el administrador de la plataforma gestiona el número compartido.
        </p>
      </div>
    )
  }

  const state = status?.state ?? 'offline'

  const handleConnect = async () => {
    setQrDataUrl(null)
    setPairingCode(null)
    const result = await connect.mutateAsync()
    const qr = result?.base64 ?? result?.qrcode?.code ?? result?.code ?? null
    if (qr) {
      setQrDataUrl(qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}`)
    } else if (result?.pairingCode) {
      setPairingCode(result.pairingCode)
    }
  }

  const handleDisconnect = () => {
    if (
      !window.confirm(
        '¿Desconectar el WhatsApp compartido? NINGÚN negocio podrá enviar ni recibir mensajes hasta que se vincule de nuevo.'
      )
    ) {
      return
    }
    setQrDataUrl(null)
    setPairingCode(null)
    disconnect.mutate()
  }

  const handleTestSend = () => {
    setTestResult(null)
    testSend.mutate(
      { number: testNumber, text: testText },
      {
        onSuccess: () => setTestResult('Mensaje de prueba enviado ✓'),
        onError: (err) => setTestResult(`Error: ${err.message}`),
      }
    )
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Plataforma</h1>
        <p className="mt-1 text-sm text-linen-600">
          El número de WhatsApp compartido por todos tus clientes y la
          infraestructura del asistente.
        </p>
      </div>

      {/* Número compartido */}
      <Card className="mb-6 p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className={`h-3 w-3 rounded-full ${stateDot(state)}`} />
            <div>
              <div className="text-base font-semibold text-ink">{stateLabel(state)}</div>
              <div className="tabular text-xs text-linen-600">
                instancia: {status?.instance ?? '—'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(state === 'open' || state === 'connecting') && (
              <Button
                type="button"
                variant="outline"
                onClick={handleDisconnect}
                disabled={disconnect.isLoading}
                className="border-lacre/40 text-lacre hover:bg-lacre-wash"
              >
                <IconPower className="h-4 w-4" />
                {disconnect.isLoading ? 'Desconectando…' : 'Desconectar'}
              </Button>
            )}
            <Button
              type="button"
              onClick={handleConnect}
              disabled={connect.isLoading || state === 'open'}
            >
              <IconWifi className="h-4 w-4" />
              {state === 'open' ? 'Conectado' : connect.isLoading ? 'Generando QR…' : 'Vincular número'}
            </Button>
          </div>
        </div>
        {(connect.error || disconnect.error) && (
          <div className="mt-3 space-y-2">
            {connect.error && <ErrorSlip message={connect.error.message} />}
            {disconnect.error && <ErrorSlip message={disconnect.error.message} />}
          </div>
        )}
      </Card>

      {/* QR de emparejamiento */}
      {qrDataUrl && state !== 'open' && (
        <Card className="mb-6 p-6">
          <h2 className="text-sm font-semibold text-ink">Escanea este código</h2>
          <div className="mt-3 flex flex-col items-center gap-3 sm:flex-row sm:items-start">
            <img
              src={qrDataUrl}
              alt="Código QR de WhatsApp"
              className="h-56 w-56 rounded-md border border-linen-200 bg-white p-2"
            />
            <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-soft">
              <li>Abre WhatsApp en el teléfono a vincular</li>
              <li>Toca <span className="font-semibold">Adjuntar → Dispositivos vinculados</span></li>
              <li>Toca <span className="font-semibold">Vincular un dispositivo</span> y escanea</li>
            </ol>
          </div>
          <p className="mt-3 text-xs text-linen-600">
            El panel detecta la conexión solo en unos segundos.
          </p>
        </Card>
      )}

      {pairingCode && state !== 'open' && (
        <Card className="mb-6 p-6">
          <h2 className="text-sm font-semibold text-ink">Código de emparejamiento</h2>
          <p className="tabular mt-2 text-2xl font-bold tracking-[0.3em] text-pine">
            {pairingCode}
          </p>
        </Card>
      )}

      {/* Prueba de envío */}
      {isAdmin && (
        <Card className="p-5">
          <h2 className="text-sm font-semibold text-ink">Enviar prueba</h2>
          <p className="mt-1 text-xs text-linen-600">
            Comprueba que el canal envía mensajes reales.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <div className="w-48">
              <label className="mb-1 block text-xs font-medium text-ink-soft" htmlFor="test-number">
                Número de destino
              </label>
              <Input
                id="test-number"
                value={testNumber}
                onChange={(e) => setTestNumber(e.target.value)}
                placeholder="573001112233"
                aria-label="Número de destino"
              />
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="mb-1 block text-xs font-medium text-ink-soft" htmlFor="test-text">
                Mensaje
              </label>
              <Input
                id="test-text"
                value={testText}
                onChange={(e) => setTestText(e.target.value)}
                aria-label="Mensaje de prueba"
              />
            </div>
            <Button
              type="button"
              onClick={handleTestSend}
              disabled={testSend.isLoading || testNumber.trim().length < 8}
            >
              {testSend.isLoading ? 'Enviando…' : 'Enviar'}
            </Button>
          </div>
          {testResult && (
            <p className={`mt-3 text-sm ${testResult.startsWith('Error') ? 'text-lacre' : 'text-ok'}`}>
              {testResult}
            </p>
          )}
        </Card>
      )}

      )}
        </Card>
      )}

      {/* Configuración IA (guardián + manual) */}
      <Card className="mb-6 p-5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <IconBrain className="h-5 w-5 text-pine" />
            <h2 className="text-sm font-semibold text-ink">Proveedores IA (LLM / STT / TTS)</h2>
          </div>
          {aiLoading && (
            <IconRefreshCw className="h-4 w-4 text-linen-400 animate-spin" />
          )}
        </div>
        <p className="mt-1 text-xs text-linen-600">
          El guardián LLM monitorea fallos cada 10 min y cambia proveedor/modelo
          automáticamente. Aquí ves la config actual y puedes forzar cambios.
        </p>
        {(aiError || updateAI.error) && (
          <div className="mt-3 space-y-2">
            {aiError && <ErrorSlip message={aiError.message} />}
            {updateAI.error && <ErrorSlip message={updateAI.error.message} />}
          </div>
        )}
        {aiConfig && (
          <div className="mt-3 space-y-3">
            {Object.entries(aiConfig).map(([key, item]) => (
              <div
                key={key}
                className="flex flex-wrap items-center gap-3 p-3 bg-linen-50 rounded-lg"
              >
                <div className="min-w-[180px] flex items-center gap-2">
                  {item.is_secret && (
                    <IconKey className="h-3.5 w-3.5 text-linen-400" />
                  )}
                  <span className="text-xs font-medium text-ink-soft">{key}</span>
                </div>
                <span className="flex-1 min-w-[150px] truncate text-sm text-ink font-mono">
                  {item.is_secret ? (item.value ? '••••••••' : '—') : (item.value || '—')}
                </span>
                {item.label && (
                  <span className="text-xs text-linen-500">{item.label}</span>
                )}
                <div className="flex items-center gap-2">
                  {editingKey === key ? (
                    <>
                      <Input
                        type={item.value_type === 'url' ? 'url' : 'text'}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="w-64"
                        aria-label={`Valor para ${key}`}
                      />
                      <Button
                        size="sm"
                        onClick={() => {
                          updateAI.mutate({ key, value: editValue })
                          setEditingKey(null)
                        }}
                        disabled={updateAI.isLoading}
                      >
                        Guardar
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setEditingKey(null)}
                      >
                        Cancelar
                      </Button>
                    </>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditingKey(key)
                        setEditValue(item.value)
                      }}
                    >
                      Editar
                    </Button>
                  )}
                </div>
              </div>
            ))}
          )}
        )}
        {!aiConfig && !aiLoading && (
          <p className="mt-3 text-center text-sm text-linen-500">
            Sin configuración cargada.
          </p>
        )}
      </Card>

      <p className="mt-4 text-xs text-linen-600">
        Próximamente aquí: auditoría de la plataforma y estado de los servicios.
      </p>
    </div>
  )
}
