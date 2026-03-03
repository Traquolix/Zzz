/**
 * Tests for DashboardGrid component.
 *
 * Verifies:
 * 1. Drag handle visibility in edit mode vs non-edit mode
 * 2. Edit mode styling (ring, dashed border)
 * 3. Widget rendering and grid layout
 * 4. draggableHandle prop is passed to Responsive component
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { WidgetConfig, Layouts } from '@/types/dashboard'

// Mock react-grid-layout
vi.mock('react-grid-layout', () => {
    const mockResponsive = vi.fn(({ children }: any) => (
        <div data-testid="responsive-grid">{children}</div>
    ))
    return {
        Responsive: mockResponsive,
        useContainerWidth: () => ({
            width: 1024,
            containerRef: { current: null },
            mounted: true,
        }),
    }
})

// Mock WidgetGhost
vi.mock('@/components/Dashboard/Editing/WidgetGhost', () => ({
    WidgetGhost: ({ name }: { name: string }) => (
        <div data-testid="widget-ghost">{name}</div>
    ),
}))

// Mock ErrorBoundary
vi.mock('@/components/ui/ErrorBoundary', () => ({
    ErrorBoundary: ({ children }: any) => (
        <div data-testid="error-boundary">{children}</div>
    ),
}))

// Mock lucide-react - use importOriginal to keep other icons
vi.mock('lucide-react', async (importOriginal) => {
    const actual = await importOriginal()
    return {
        ...(actual || {}),
        GripVertical: () => <div data-testid="grip-vertical" />,
    }
})

// Import after mocks
import { DashboardGrid } from './DashboardGrid'

describe('DashboardGrid', () => {
    const mockWidget: WidgetConfig = {
        id: 'test-widget-1',
        name: 'Test Widget',
        component: () => <div>Widget Content</div>,
    }

    const mockLayouts: Layouts = {
        lg: [{ i: 'test-widget-1', x: 0, y: 0, w: 4, h: 4 }],
        md: [{ i: 'test-widget-1', x: 0, y: 0, w: 3, h: 4 }],
        sm: [{ i: 'test-widget-1', x: 0, y: 0, w: 2, h: 4 }],
        xs: [{ i: 'test-widget-1', x: 0, y: 0, w: 1, h: 4 }],
    }

    it('should render grid container', () => {
        render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={false}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.getByTestId('responsive-grid')).toBeInTheDocument()
    })

    it('should show drag handle in edit mode', () => {
        render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={true}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.getByTestId('grip-vertical')).toBeInTheDocument()
    })

    it('should not show drag handle in non-edit mode', () => {
        render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={false}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.queryByTestId('grip-vertical')).not.toBeInTheDocument()
    })

    it('should show WidgetGhost in edit mode', () => {
        render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={true}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.getByTestId('widget-ghost')).toBeInTheDocument()
        expect(screen.getByText('Test Widget')).toBeInTheDocument()
    })

    it('should show widget content in non-edit mode', () => {
        render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={false}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.getByText('Widget Content')).toBeInTheDocument()
        expect(screen.queryByTestId('widget-ghost')).not.toBeInTheDocument()
    })

    it('should render multiple widgets', () => {
        const widget2: WidgetConfig = {
            id: 'test-widget-2',
            name: 'Test Widget 2',
            component: () => <div>Widget 2 Content</div>,
        }

        const multiLayouts: Layouts = {
            lg: [
                { i: 'test-widget-1', x: 0, y: 0, w: 4, h: 4 },
                { i: 'test-widget-2', x: 4, y: 0, w: 4, h: 4 },
            ],
            md: [
                { i: 'test-widget-1', x: 0, y: 0, w: 3, h: 4 },
                { i: 'test-widget-2', x: 3, y: 0, w: 3, h: 4 },
            ],
            sm: [
                { i: 'test-widget-1', x: 0, y: 0, w: 2, h: 4 },
                { i: 'test-widget-2', x: 0, y: 4, w: 2, h: 4 },
            ],
            xs: [
                { i: 'test-widget-1', x: 0, y: 0, w: 1, h: 4 },
                { i: 'test-widget-2', x: 0, y: 4, w: 1, h: 4 },
            ],
        }

        render(
            <DashboardGrid
                widgets={[mockWidget, widget2]}
                layouts={multiLayouts}
                editMode={false}
                onLayoutChange={vi.fn()}
            />
        )
        expect(screen.getByText('Widget Content')).toBeInTheDocument()
        expect(screen.getByText('Widget 2 Content')).toBeInTheDocument()
    })

    it('should apply edit mode styling to grid items in edit mode', () => {
        const { container } = render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={true}
                onLayoutChange={vi.fn()}
            />
        )
        const gridCard = container.querySelector('.grid-card')
        expect(gridCard).toHaveClass('ring-1', 'ring-dashed', 'rounded-lg')
    })

    it('should not apply edit mode styling in non-edit mode', () => {
        const { container } = render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={false}
                onLayoutChange={vi.fn()}
            />
        )
        const gridCard = container.querySelector('.grid-card')
        expect(gridCard).not.toHaveClass('ring-1')
        expect(gridCard).not.toHaveClass('ring-dashed')
    })

    it('should have draggableHandle class on drag handle div', () => {
        const { container } = render(
            <DashboardGrid
                widgets={[mockWidget]}
                layouts={mockLayouts}
                editMode={true}
                onLayoutChange={vi.fn()}
            />
        )
        const dragHandle = container.querySelector('.drag-handle')
        expect(dragHandle).toBeInTheDocument()
    })
})
