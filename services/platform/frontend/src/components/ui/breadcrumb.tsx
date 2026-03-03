import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

type BreadcrumbItem = {
    label: string
    href?: string  // If no href, it's the current page (non-clickable)
}

type BreadcrumbProps = {
    items: BreadcrumbItem[]
}

export function Breadcrumb({ items }: BreadcrumbProps) {
    if (items.length <= 1) return null  // Don't show for root pages

    return (
        <nav aria-label="Breadcrumb" className="px-4 py-2 text-sm">
            <ol className="flex items-center gap-1.5 text-muted-foreground">
                {items.map((item, index) => (
                    <li key={index} className="flex items-center gap-1.5">
                        {index > 0 && (
                            <ChevronRight className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                        )}
                        {item.href ? (
                            <Link
                                to={item.href}
                                className="hover:text-foreground transition-colors"
                            >
                                {item.label}
                            </Link>
                        ) : (
                            <span className="text-foreground font-medium" aria-current="page">
                                {item.label}
                            </span>
                        )}
                    </li>
                ))}
            </ol>
        </nav>
    )
}

export type { BreadcrumbItem }
