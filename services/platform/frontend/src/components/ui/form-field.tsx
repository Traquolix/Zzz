import { type InputHTMLAttributes, type ReactNode, forwardRef, useId } from 'react'
import { cn } from '@/lib/utils'

type FormFieldProps = InputHTMLAttributes<HTMLInputElement> & {
    label: string
    error?: string
    touched?: boolean
    hint?: string
    leadingIcon?: ReactNode
}

export const FormField = forwardRef<HTMLInputElement, FormFieldProps>(
    ({ label, error, touched, hint, leadingIcon, className, id: externalId, ...inputProps }, ref) => {
        const generatedId = useId()
        const id = externalId || generatedId
        const errorId = `${id}-error`
        const hintId = `${id}-hint`
        const showError = touched && error

        return (
            <div className="space-y-1.5">
                <label
                    htmlFor={id}
                    className="block text-sm font-medium text-slate-700 dark:text-slate-300"
                >
                    {label}
                    {inputProps.required && (
                        <span className="text-destructive ml-0.5" aria-hidden="true">*</span>
                    )}
                </label>
                <div className="relative">
                    {leadingIcon && (
                        <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" aria-hidden="true">
                            {leadingIcon}
                        </div>
                    )}
                    <input
                        ref={ref}
                        id={id}
                        className={cn(
                            'w-full rounded-md border px-3 py-2 text-sm transition-colors',
                            'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100',
                            'placeholder:text-slate-400 dark:placeholder:text-slate-500',
                            'focus:outline-none focus:ring-2 focus:ring-ring',
                            showError
                                ? 'border-destructive focus:ring-destructive/50'
                                : 'border-input hover:border-slate-400 dark:hover:border-slate-500',
                            leadingIcon && 'pl-10',
                            className
                        )}
                        aria-invalid={showError ? 'true' : undefined}
                        aria-describedby={[
                            showError ? errorId : null,
                            hint ? hintId : null,
                        ].filter(Boolean).join(' ') || undefined}
                        {...inputProps}
                    />
                </div>
                {showError && (
                    <p id={errorId} className="text-xs text-destructive" role="alert">
                        {error}
                    </p>
                )}
                {hint && !showError && (
                    <p id={hintId} className="text-xs text-muted-foreground">
                        {hint}
                    </p>
                )}
            </div>
        )
    }
)
FormField.displayName = 'FormField'
