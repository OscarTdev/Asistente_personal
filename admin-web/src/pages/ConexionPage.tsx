// Conexión WhatsApp: estado de la instancia, QR para vincular el número y
// envío de prueba. Solo administradores.

import { useState } from 'react'
import Card from '../components/ui/card'
import Button from '../components/ui/button'
import Input from '../components/ui/input'
import ErrorSlip from '../components/ui/error-slip'
import { IconWifi } from '../components/ui/icons'
import { useAuth } from '../auth/AuthContext'
import { useConnectWhatsapp, useTestSendWhatsapp, useWhatsappStatus } from '../hooks/useWhatsapp'

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

export default function ConexionPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const { data: status } = useWhatsappStatus()
  const connect = useConnectWhatsapp()
  const testSend = useTestSendWhatsapp()

  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [pairingCode, setPairingCode] = useState<string | null>(null)
  const [testNumber, setTestNumber] = useState('')
  const [testText, setTestText] = useState('¡Hola! Soy el asistente Aura en pruebas 🛠')
  const [testResult, setTestResult] = useState<string | null>(null)

  if (!isAdmin) {
    return (
      <div className="ficha px-6 py-8 text-center">
        <p className="text-sm text-ink-soft">
          Solo los administradores gestionan la conexión de WhatsApp.
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
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Conexión WhatsApp</h1>
        <p className="mt-1 text-sm text-linen-600">
          Vincula el número que usará el asistente para conversar con tus clientes.
        </p>
      </div>

      {/* Estado de la instancia */}
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
          <Button
            type="button"
            onClick={handleConnect}
            disabled={connect.isLoading || state === 'open'}
          >
            <IconWifi className="h-4 w-4" />
            {state === 'open' ? 'Conectado' : connect.isLoading ? 'Generando QR…' : 'Vincular número'}
          </Button>
        </div>
        {connect.error && (
          <div className="mt-3">
            <ErrorSlip message={connect.error.message} />
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
              onChangeValue={(value) => setTestNumber(value)}
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
              onChangeValue={setTestText}
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
    </div>
  )
}
