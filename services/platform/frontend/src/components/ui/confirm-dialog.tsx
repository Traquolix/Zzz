import { createContext, useContext, useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import { Button } from './button'
import i18n from '@/i18n'

type ConfirmOptions = {
    title?: string
    message: string
    confirmText?: string
    cancelText?: string
    variant?: 'default' | 'destructive'
}

type ConfirmContextType = {
    confirm: (options: ConfirmOptions) => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmContextType | null>(null)

export function useConfirm() {
    const context = useContext(ConfirmContext)
    if (!context) {
        throw new Error('useConfirm must be used within ConfirmDialogProvider')
    }
    return context.confirm
}

type DialogState = ConfirmOptions & {
    resolve: (value: boolean) => void
}

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
    const [dialog, setDialog] = useState<DialogState | null>(null)
    const dialogContentRef = useRef<HTMLDivElement>(null)

    const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
        return new Promise((resolve) => {
            setDialog({ ...options, resolve })
        })
    }, [])

    const handleConfirm = () => {
        dialog?.resolve(true)
        setDialog(null)
    }

    const handleCancel = () => {
        dialog?.resolve(false)
        setDialog(null)
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            handleCancel()
        } else if (e.key === 'Enter') {
            handleConfirm()
        }
    }

    // Focus trap: keep focus within dialog when open
    useEffect(() => {
        if (!dialog) return

        const focusableElements = dialogContentRef.current?.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        const firstElement = focusableElements?.[0] as HTMLElement
        const lastElement = focusableElements?.[focusableElements.length - 1] as HTMLElement

        // Focus the confirm button by default
        const confirmButton = dialogContentRef.current?.querySelector('button:last-of-type') as HTMLElement
        confirmButton?.focus()

        const handleTabKey = (e: KeyboardEvent) => {
            if (e.key !== 'Tab') return

            if (e.shiftKey) {
                // Shift + Tab
                if (document.activeElement === firstElement) {
                    e.preventDefault()
                    lastElement?.focus()
                }
            } else {
                // Tab
                if (document.activeElement === lastElement) {
                    e.preventDefault()
                    firstElement?.focus()
                }
            }
        }

        document.addEventListener('keydown', handleTabKey)
        return () => {
            document.removeEventListener('keydown', handleTabKey)
        }
    }, [dialog])

    return (
        <ConfirmContext.Provider value={{ confirm }}>
            {children}
            {dialog && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-[2000] animate-in fade-in-0 duration-150"
                    onKeyDown={handleKeyDown}
                    onClick={handleCancel}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby={dialog.title ? 'confirm-dialog-title' : undefined}
                    aria-describedby="confirm-dialog-message"
                >
                    <div ref={dialogContentRef} className="bg-white dark:bg-slate-900 rounded-lg p-5 shadow-xl min-w-[320px] max-w-[400px] mx-4 animate-in zoom-in-95 fade-in-0 duration-200" onClick={e => e.stopPropagation()}>
                        {dialog.title && (
                            <h3 id="confirm-dialog-title" className="text-lg font-semibold mb-2 text-slate-800 dark:text-slate-100">
                                {dialog.title}
                            </h3>
                        )}
                        <p id="confirm-dialog-message" className="text-slate-600 dark:text-slate-300 mb-5">{dialog.message}</p>
                        <div className="flex justify-end gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleCancel}
                            >
                                {dialog.cancelText || i18n.t('common.cancel', 'Cancel')}
                            </Button>
                            <Button
                                variant={dialog.variant === 'destructive' ? 'destructive' : 'default'}
                                size="sm"
                                onClick={handleConfirm}
                            >
                                {dialog.confirmText || i18n.t('common.confirm', 'Confirm')}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </ConfirmContext.Provider>
    )
}
