type Props = {
    children: React.ReactNode
    className?: string
}

export function ScrollableTable({ children, className = '' }: Props) {
    return (
        <div className={`overflow-x-auto -mx-4 px-4 ${className}`}>
            {children}
        </div>
    )
}
