import { Component, type ReactNode } from 'react'
import i18next from 'i18next'
import { logger } from '@/lib/logger'

type PanelErrorBoundaryProps = {
  children: ReactNode
}

type PanelErrorBoundaryState = {
  hasError: boolean
}

/**
 * Compact error boundary for sidebar panels.
 * Catches render errors in a single panel without crashing the entire sidebar.
 */
export class PanelErrorBoundary extends Component<PanelErrorBoundaryProps, PanelErrorBoundaryState> {
  constructor(props: PanelErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): PanelErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    logger.error('PanelErrorBoundary caught an error:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-12 px-4 text-center">
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--proto-text-muted)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="text-[length:var(--text-sm)] text-[var(--proto-text-muted)]">
            {i18next.t('common.somethingWentWrong')}
          </span>
          <button
            onClick={this.handleRetry}
            className="px-3 py-1.5 rounded text-[length:var(--text-xs)] font-medium text-[var(--proto-text-secondary)] bg-[var(--proto-surface-raised)] hover:text-[var(--proto-text)] transition-colors cursor-pointer"
          >
            {i18next.t('common.tryAgain')}
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
