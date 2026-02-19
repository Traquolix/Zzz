import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { Button } from './button'

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

    return (
        <ConfirmContext.Provider value={{ confirm }}>
            {children}
            {dialog && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-[2000]"
                    onKeyDown={handleKeyDown}
                    onClick={handleCancel}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby={dialog.title ? 'confirm-dialog-title' : undefined}
                    aria-describedby="confirm-dialog-message"
                >
                    <div className="bg-white rounded-lg p-5 shadow-xl min-w-[320px] max-w-[400px]" onClick={e => e.stopPropagation()}>
                        {dialog.title && (
                            <h3 id="confirm-dialog-title" className="text-lg font-semibold mb-2 text-slate-800">
                                {dialog.title}
                            </h3>
                        )}
                        <p id="confirm-dialog-message" className="text-slate-600 mb-5">{dialog.message}</p>
                        <div className="flex justify-end gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleCancel}
                            >
                                {dialog.cancelText || 'Cancel'}
                            </Button>
                            <Button
                                variant={dialog.variant === 'destructive' ? 'destructive' : 'default'}
                                size="sm"
                                onClick={handleConfirm}
                                autoFocus
                            >
                                {dialog.confirmText || 'Confirm'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </ConfirmContext.Provider>
    )
}
