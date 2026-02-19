import { Move } from 'lucide-react'

type Props = {
    name: string
}

export function WidgetGhost({ name }: Props) {
    return (
        <div className="h-full w-full bg-slate-100 flex flex-col items-center justify-center gap-2 text-slate-500">
            <Move className="h-6 w-6" />
            <span className="text-sm font-medium">{name}</span>
        </div>
    )
}