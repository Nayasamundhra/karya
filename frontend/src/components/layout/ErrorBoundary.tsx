import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from '@/components/ui/Button'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * The last-resort fallback for a render-time exception React Query/router
 * error handling never sees — a bug in a component's own render, not a
 * failed request. Class component because React has no hook equivalent for
 * `componentDidCatch` as of this writing; this is the one place in the
 * codebase that needs one.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled render error', error, info.componentStack)
  }

  override render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-4 text-center">
          <h1 className="text-lg font-semibold text-foreground">Something went wrong</h1>
          <p className="max-w-sm text-sm text-foreground-muted">
            Karya ran into an unexpected problem. Reloading usually fixes this.
          </p>
          <Button onClick={() => window.location.reload()}>Reload</Button>
        </div>
      )
    }
    return this.props.children
  }
}
