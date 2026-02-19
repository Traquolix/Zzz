import { type Layout, Responsive, useContainerWidth } from "react-grid-layout"
import { BREAKPOINTS, COLS } from "@/constants/dashboard"
import type { Layouts, WidgetConfig } from "@/types/dashboard"
import { WidgetGhost } from "@/components/Dashboard/Editing/WidgetGhost"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
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
                >
                    {widgets.map(widget => {
                        const Component = widget.component
                        return (
                            <div
                                key={widget.id}
                                className={`grid-card h-full ${editMode ? 'editable' : ''}`}
                                onContextMenu={(e) => handleContextMenu(e, widget.id)}
                            >
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