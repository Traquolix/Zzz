import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ThemeToggle } from './ThemeToggle'
import { TooltipProvider } from '@/components/ui/tooltip'

describe('ThemeToggle', () => {
    beforeEach(() => {
        localStorage.clear()
        document.documentElement.className = ''
    })

    afterEach(() => {
        localStorage.clear()
        document.documentElement.className = ''
    })

    it('renders a button with aria-label', () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')
        expect(button).toHaveAttribute('aria-label')
    })

    it('renders an icon in the button', () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')
        const icon = button.querySelector('svg')
        expect(icon).toBeInTheDocument()
    })

    it('cycles through light → sequoia → light', async () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')

        // Start in light mode
        expect(document.documentElement.classList.contains('sequoia')).toBe(false)

        // Click 1: light → sequoia
        fireEvent.click(button)
        await waitFor(() => {
            expect(document.documentElement.classList.contains('sequoia')).toBe(true)
        })

        // Click 2: sequoia → light
        fireEvent.click(button)
        await waitFor(() => {
            expect(document.documentElement.classList.contains('sequoia')).toBe(false)
        })
    })

    it('persists theme preference to localStorage', async () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')

        fireEvent.click(button)
        await waitFor(() => {
            expect(localStorage.getItem('sequoia_theme')).toBe('sequoia')
        })

        fireEvent.click(button)
        await waitFor(() => {
            expect(localStorage.getItem('sequoia_theme')).toBe('light')
        })
    })

    it('restores sequoia theme from localStorage on mount', () => {
        localStorage.setItem('sequoia_theme', 'sequoia')
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)

        expect(document.documentElement.classList.contains('sequoia')).toBe(true)
    })

    it('defaults to light when no localStorage value exists', () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)

        expect(document.documentElement.classList.contains('sequoia')).toBe(false)
        expect(document.documentElement.classList.contains('dark')).toBe(false)
    })

    it('changes aria-label based on theme state', async () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')

        // Light mode → shows "Switch to SequoIA theme"
        expect(button).toHaveAttribute('aria-label', 'Switch to SequoIA theme')

        fireEvent.click(button)
        await waitFor(() => {
            expect(button).toHaveAttribute('aria-label', 'Switch to light mode')
        })
    })

    it('button has hover styling classes', () => {
        render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
        const button = screen.getByRole('button')

        expect(button.className).toContain('hover:bg-slate-200')
    })

    it('adds theme-transitioning class on toggle', () => {
        vi.useFakeTimers()
        try {
            render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
            const button = screen.getByRole('button')

            fireEvent.click(button)

            // Check that theme-transitioning was added immediately after click
            expect(document.documentElement.classList.contains('theme-transitioning')).toBe(true)
        } finally {
            vi.useRealTimers()
        }
    })

    it('removes theme-transitioning class after delay', () => {
        vi.useFakeTimers()
        try {
            render(<TooltipProvider><ThemeToggle /></TooltipProvider>)
            const button = screen.getByRole('button')

            fireEvent.click(button)

            expect(document.documentElement.classList.contains('theme-transitioning')).toBe(true)

            vi.advanceTimersByTime(300)

            expect(document.documentElement.classList.contains('theme-transitioning')).toBe(false)
        } finally {
            vi.useRealTimers()
        }
    })
})
