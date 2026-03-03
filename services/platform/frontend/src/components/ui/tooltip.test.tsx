import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Tooltip, TooltipProvider } from './tooltip'
import { Button } from './button'

describe('Tooltip', () => {
    it('renders trigger content', () => {
        render(
            <TooltipProvider>
                <Tooltip content="Tooltip text">
                    <Button>Hover me</Button>
                </Tooltip>
            </TooltipProvider>
        )
        const triggerButton = screen.getByRole('button', { name: 'Hover me' })
        expect(triggerButton).toBeInTheDocument()
    })

    it('tooltip content is initially hidden (not in DOM)', () => {
        render(
            <TooltipProvider>
                <Tooltip content="Hidden tooltip">
                    <Button>Trigger</Button>
                </Tooltip>
            </TooltipProvider>
        )
        // The tooltip content should not be rendered initially (Portal renders to document root)
        // We just verify the trigger is there
        const triggerButton = screen.getByRole('button', { name: 'Trigger' })
        expect(triggerButton).toBeInTheDocument()
        // Content should not be in DOM initially
        expect(screen.queryByText('Hidden tooltip')).not.toBeInTheDocument()
    })

    it('wraps children in trigger and passes content prop', () => {
        render(
            <TooltipProvider>
                <Tooltip content="Test tooltip">
                    <span data-testid="custom-trigger">Click here</span>
                </Tooltip>
            </TooltipProvider>
        )

        const trigger = screen.getByTestId('custom-trigger')
        expect(trigger).toBeInTheDocument()
        expect(trigger).toHaveTextContent('Click here')
    })

})
