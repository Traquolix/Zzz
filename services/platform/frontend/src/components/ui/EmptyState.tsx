import type { ReactNode } from 'react'

type EmptyStateProps = {
    icon?: ReactNode
    title: string
    description?: string
    action?: ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            {icon && <div className="mb-4 text-slate-400">{icon}</div>}
            <h3 className="text-lg font-medium text-slate-700 dark:text-slate-300">{title}</h3>
            {description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>}
            {action && <div className="mt-4">{action}</div>}
        </div>
    )
}
