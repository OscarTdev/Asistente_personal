// ErrorBoundary: cuando el render crashea, el dueño ve una errata de lacre
// con un botón para volver al panel — nunca una pantalla blanca silenciosa.
// DESIGN.md: los errores son notas de lacre persistentes, no toasts.

import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('ErrorBoundary capturó:', error, info.componentStack)
  }

  private handleReset = () => {
    this.setState({ hasError: false, message: null })
  }

  private handleGoHome = () => {
    window.location.href = '/'
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <div
          className="w-full max-w-md rounded-lg border p-6"
          style={{
            background: 'var(--color-panel, #fffdf8)',
            borderColor: '#ecc8c1',
          }}
        >
          <p
            className="mb-2 text-[11px] font-bold uppercase"
            style={{ color: 'var(--color-lacre, #9c2f26)', letterSpacing: '0.09em' }}
          >
            Errata
          </p>
          <h2 className="mb-2 text-lg font-semibold" style={{ color: 'var(--color-ink, #211e18)' }}>
            Algo se descosió en esta pantalla
          </h2>
          <p className="mb-5 text-sm" style={{ color: 'var(--color-ink-soft, #4c473c)' }}>
            El resto del panel sigue funcionando. Puedes volver al escritorio e intentar
            de nuevo; si el problema persiste, revisa la consola del navegador.
          </p>
          {this.state.message && (
            <p
              className="mb-4 break-words rounded-md px-3 py-2 font-mono text-xs"
              style={{ background: 'rgba(156,47,38,0.06)', color: 'var(--color-lacre, #9c2f26)' }}
            >
              {this.state.message}
            </p>
          )}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={this.handleGoHome}
              className="h-10 rounded-md px-4 text-sm font-medium"
              style={{ background: 'var(--color-pine, #1d4433)', color: '#f4f1e9' }}
            >
              Volver al panel
            </button>
            <button
              type="button"
              onClick={this.handleReset}
              className="h-10 rounded-md border px-4 text-sm font-medium"
              style={{
                borderColor: 'var(--color-linen-300, #d6cdb4)',
                background: 'transparent',
                color: 'var(--color-ink, #211e18)',
              }}
            >
              Reintentar
            </button>
          </div>
        </div>
      </div>
    )
  }
}
