import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string, defaultValue?: string) => defaultValue || key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
}))

// Mock i18n directly
vi.mock('@/i18n', () => ({
    default: {
        t: (key: string, fallback?: string) => fallback || key,
    },
}))

import { ConfirmDialogProvider, useConfirm } from './confirm-dialog'

describe('ConfirmDialog', () => {
    it('renders without errors when no dialog is shown', () => {
        const { container } = render(
            <ConfirmDialogProvider>
                <div>Content</div>
            </ConfirmDialogProvider>
        )
        expect(container.textContent).toContain('Content')
    })

    it('shows dialog when confirm is called', async () => {
        function TestComponent() {
            const confirm = useConfirm()
            return <button onClick={() => confirm({ message: 'Test message' })}>Open</button>
        }

        const { container } = render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        const button = screen.getByText('Open')
        fireEvent.click(button)

        await waitFor(() => {
            expect(container.textContent).toContain('Test message')
        })
    })

    it('uses default button texts from i18n', async () => {
        function TestComponent() {
            const confirm = useConfirm()
            return <button onClick={() => confirm({ message: 'Test message' })}>Open</button>
        }

        render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        fireEvent.click(screen.getByText('Open'))

        await waitFor(() => {
            const buttons = screen.getAllByRole('button')
            const cancelButton = buttons.find(b => b.textContent?.includes('Cancel'))
            const confirmButton = buttons.find(b => b.textContent?.includes('Confirm'))
            expect(cancelButton).toBeInTheDocument()
            expect(confirmButton).toBeInTheDocument()
        })
    })

    it('uses custom button texts when provided', async () => {
        function TestComponent() {
            const confirm = useConfirm()
            return (
                <button
                    onClick={() =>
                        confirm({
                            message: 'Delete?',
                            cancelText: 'Keep',
                            confirmText: 'Delete',
                        })
                    }
                >
                    Open
                </button>
            )
        }

        render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        fireEvent.click(screen.getByText('Open'))

        await waitFor(() => {
            expect(screen.getByText('Keep')).toBeInTheDocument()
            expect(screen.getByText('Delete')).toBeInTheDocument()
        })
    })

    it('resolves with true when confirm is clicked', async () => {
        let resultPromise: Promise<boolean> | null = null
        function TestComponent() {
            const confirm = useConfirm()
            return (
                <button
                    onClick={async () => {
                        resultPromise = confirm({ message: 'Test message' })
                    }}
                >
                    Open
                </button>
            )
        }

        render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        fireEvent.click(screen.getByText('Open'))

        await waitFor(() => {
            const buttons = screen.getAllByRole('button')
            const confirmButton = buttons[buttons.length - 1]
            fireEvent.click(confirmButton)
        })

        const result = await resultPromise
        expect(result).toBe(true)
    })

    it('resolves with false when cancel is clicked', async () => {
        let resultPromise: Promise<boolean> | null = null
        function TestComponent() {
            const confirm = useConfirm()
            return (
                <button
                    onClick={async () => {
                        resultPromise = confirm({ message: 'Test message' })
                    }}
                >
                    Open
                </button>
            )
        }

        render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        fireEvent.click(screen.getByText('Open'))

        await waitFor(() => {
            const buttons = screen.getAllByRole('button')
            const cancelButton = buttons[buttons.length - 2]
            fireEvent.click(cancelButton)
        })

        const result = await resultPromise
        expect(result).toBe(false)
    })

    it('closes on Escape key', async () => {
        function TestComponent() {
            const confirm = useConfirm()
            return <button onClick={() => confirm({ message: 'Test message' })}>Open</button>
        }

        const { container } = render(
            <ConfirmDialogProvider>
                <TestComponent />
            </ConfirmDialogProvider>
        )

        fireEvent.click(screen.getByText('Open'))

        await waitFor(() => {
            expect(screen.getByText('Test message')).toBeInTheDocument()
        })

        const dialog = container.querySelector('[role="dialog"]')
        fireEvent.keyDown(dialog!, { key: 'Escape' })

        await waitFor(() => {
            expect(screen.queryByText('Test message')).not.toBeInTheDocument()
        }, { timeout: 500 })
    })
})
