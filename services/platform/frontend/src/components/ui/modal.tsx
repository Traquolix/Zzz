import { useRef, useEffect, type ReactNode } from 'react'

type ModalProps = {
  open: boolean
  onClose: () => void
  children: ReactNode
  className?: string
  /** Full screen on mobile */
  mobileFullScreen?: boolean
}

export function Modal({ open, onClose, children, className = '', mobileFullScreen = false }: ModalProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const previousActiveElement = useRef<HTMLElement | null>(null)

  // Focus trap and keyboard handling
  useEffect(() => {
    if (!open) return
    previousActiveElement.current = document.activeElement as HTMLElement

    // Focus first focusable element
    const timer = setTimeout(() => {
      const focusable = contentRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      ;(focusable?.[0] as HTMLElement)?.focus()
    }, 50)

    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key !== 'Tab') return

      const focusable = contentRef.current?.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable?.length) return

      const first = focusable[0] as HTMLElement
      const last = focusable[focusable.length - 1] as HTMLElement

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeydown)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('keydown', handleKeydown)
      previousActiveElement.current?.focus()
    }
  }, [open, onClose])

  if (!open) return null

  const mobileClasses = mobileFullScreen
    ? 'max-md:w-full max-md:h-dvh max-md:max-w-none max-md:rounded-none max-md:m-0'
    : ''

  return (
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center animate-in fade-in-0 duration-150"
      onClick={onClose}
      role="presentation"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" aria-hidden="true" />
      {/* Content */}
      <div
        ref={contentRef}
        className={`relative bg-white dark:bg-slate-900 rounded-lg shadow-xl animate-in zoom-in-95 fade-in-0 duration-200 max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto ${mobileClasses} ${className}`}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </div>
    </div>
  )
}
