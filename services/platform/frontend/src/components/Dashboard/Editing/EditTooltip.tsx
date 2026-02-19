import { MousePointerClick, Move } from 'lucide-react'

export function EditTooltip({ visible }: { visible: boolean }) {
    if (!visible) return null

    return (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-sm px-4 py-2 rounded-lg flex items-center gap-6 shadow-lg z-50">
            <div className="flex items-center gap-2">
                <Move className="h-4 w-4" />
                <span>Drag to move</span>
            </div>
            <div className="flex items-center gap-2">
                <MousePointerClick className="h-4 w-4" />
                <span>Right-click to delete</span>
            </div>
        </div>
    )
}