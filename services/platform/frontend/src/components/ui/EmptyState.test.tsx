import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Info } from 'lucide-react'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
    it('renders title', () => {
        render(<EmptyState title="No data found" />)
        expect(screen.getByText('No data found')).toBeInTheDocument()
    })

    it('renders title with correct styling', () => {
        render(<EmptyState title="No items" />)
        const title = screen.getByText('No items')
        expect(title.className).toContain('text-lg')
        expect(title.className).toContain('font-medium')
        expect(title.className).toContain('text-slate-700')
    })

    it('renders optional description', () => {
        render(
            <EmptyState
                title="No items"
                description="Create a new item to get started"
            />
        )
        expect(screen.getByText('Create a new item to get started')).toBeInTheDocument()
    })

    it('does not render description when not provided', () => {
        render(<EmptyState title="No items" />)
        expect(screen.queryByText(/Create a new item/)).not.toBeInTheDocument()
    })

    it('renders optional icon', () => {
        render(
            <EmptyState
                icon={<Info data-testid="test-icon" />}
                title="No items"
            />
        )
        expect(screen.getByTestId('test-icon')).toBeInTheDocument()
    })

    it('does not render icon container when icon not provided', () => {
        const { container } = render(<EmptyState title="No items" />)
        const iconContainer = container.querySelector('.mb-4')
        expect(iconContainer).toBeNull()
    })

    it('renders optional action', () => {
        render(
            <EmptyState
                title="No items"
                action={<button data-testid="action-btn">Create Item</button>}
            />
        )
        expect(screen.getByTestId('action-btn')).toBeInTheDocument()
    })

    it('does not render action when not provided', () => {
        render(<EmptyState title="No items" />)
        expect(screen.queryByTestId('action-btn')).not.toBeInTheDocument()
    })

    it('renders all parts together', () => {
        render(
            <EmptyState
                icon={<Info data-testid="icon" />}
                title="No incidents"
                description="There are no incidents to display"
                action={<button data-testid="action">Create Incident</button>}
            />
        )

        expect(screen.getByTestId('icon')).toBeInTheDocument()
        expect(screen.getByText('No incidents')).toBeInTheDocument()
        expect(screen.getByText('There are no incidents to display')).toBeInTheDocument()
        expect(screen.getByTestId('action')).toBeInTheDocument()
    })

    it('has correct container styling for centering', () => {
        const { container } = render(<EmptyState title="No items" />)
        const wrapper = container.querySelector('.flex')
        expect(wrapper?.className).toContain('flex-col')
        expect(wrapper?.className).toContain('items-center')
        expect(wrapper?.className).toContain('justify-center')
        expect(wrapper?.className).toContain('text-center')
    })

    it('description has correct dark mode styling', () => {
        render(
            <EmptyState
                title="No items"
                description="Try again later"
            />
        )
        const description = screen.getByText('Try again later')
        expect(description.className).toContain('dark:text-slate-400')
    })

    it('icon container has correct styling', () => {
        const { container } = render(
            <EmptyState
                icon={<Info />}
                title="No items"
            />
        )
        const iconContainer = container.querySelector('.mb-4')
        expect(iconContainer?.className).toContain('text-slate-400')
    })

    it('action container is positioned below description', () => {
        const { container } = render(
            <EmptyState
                title="No items"
                description="Description"
                action={<button>Action</button>}
            />
        )
        const actionContainer = container.querySelector('.mt-4')
        expect(actionContainer).toBeInTheDocument()
    })
})
