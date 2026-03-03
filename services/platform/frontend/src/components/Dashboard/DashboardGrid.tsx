import { type Layout, Responsive, useContainerWidth } from "react-grid-layout"
import { GripVertical } from "lucide-react"
import { BREAKPOINTS, COLS } from "@/constants/dashboard"
import type { Layouts, WidgetConfig } from "@/types/dashboard"
import { WidgetGhost } from "@/components/Dashboard/Editing/WidgetGhost"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { cn } from "@/lib/utils"
import * as React from "react"

import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

type Props = {
    widgets: WidgetConfig[]
    layouts: Layouts
    editMode: boolean
    onLayoutChange: (layout: Layout, allLayouts: Layouts) => void
    onDeleteWidget?: (id: string) => void
}

export function DashboardGrid({ widgets, layouts, editMode, onLayoutChange, onDeleteWidget }: Props) {
    const { width, containerRef, mounted } = useContainerWidth()

    const activeLayouts: Record<string, Layout> = Object.fromEntries(
        Object.entries(layouts).map(([bp, items]) => [
            bp,
            (items ?? []).map(item => ({
                ...item,
                static: !editMode,
                resizeHandles: ['se', 's', 'e', 'n', 'w', 'ne', 'nw', 'sw'],
            })),
        ])
    )

    const handleContextMenu = (e: React.MouseEvent, id: string) => {
        if (!editMode) return
        e.preventDefault()
        onDeleteWidget?.(id)
    }

    return (
        <div className={`flex-1 relative min-h-0 ${editMode ? 'select-none' : ''}`} ref={containerRef}>
            {mounted && (
                <Responsive
                    layouts={activeLayouts}
                    breakpoints={BREAKPOINTS}
                    cols={COLS}
                    width={width}
                    rowHeight={60}
                    margin={[16, 16]}
                    containerPadding={[16, 16]}
                    onLayoutChange={onLayoutChange}
                    {...{ draggableHandle: ".drag-handle" } as any}
                >
                    {widgets.map(widget => {
                        const Component = widget.component
                        return (
                            <div
                                key={widget.id}
                                className={cn(
                                    'grid-card h-full relative group',
                                    editMode && 'ring-1 ring-slate-200 dark:ring-slate-700 ring-dashed rounded-lg'
                                )}
                                onContextMenu={(e) => handleContextMenu(e, widget.id)}
                            >
                                {editMode && (
                                    <div className="drag-handle absolute top-0 left-0 right-0 h-6 flex items-center justify-center cursor-grab active:cursor-grabbing z-10 opacity-0 hover:opacity-100 transition-opacity">
                                        <GripVertical className="h-4 w-4 text-slate-400" />
                                    </div>
                                )}
                                {editMode ? (
                                    <WidgetGhost name={widget.name} />
                                ) : (
                                    <ErrorBoundary>
                                        <div className="h-full">
                                            <Component />
                                        </div>
                                    </ErrorBoundary>
                                )}
                            </div>
                        )
                    })}
                </Responsive>
            )}
        </div>
    )
}