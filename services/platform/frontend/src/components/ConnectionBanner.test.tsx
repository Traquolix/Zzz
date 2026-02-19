import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConnectionBanner } from './ConnectionBanner'

// Mock the useRealtime hook
vi.mock('@/hooks/useRealtime', () => ({
    useRealtime: vi.fn(),
}))

// Mock react-i18next — return the key as the translated string
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string) => key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
}))

import { useRealtime } from '@/hooks/useRealtime'

const mockedUseRealtime = vi.mocked(useRealtime)

describe('ConnectionBanner', () => {
    it('renders nothing when connected', () => {
        mockedUseRealtime.mockReturnValue({
            connected: true,
            reconnecting: false,
            subscribe: vi.fn(),
        })

        const { container } = render(<ConnectionBanner />)
        expect(container.firstChild).toBeNull()
    })

    it('shows disconnected message when not connected and not reconnecting', () => {
        mockedUseRealtime.mockReturnValue({
            connected: false,
            reconnecting: false,
            subscribe: vi.fn(),
        })

        render(<ConnectionBanner />)
        expect(screen.getByText('connection.disconnected')).toBeInTheDocument()
    })

    it('shows reconnecting message when reconnecting', () => {
        mockedUseRealtime.mockReturnValue({
            connected: false,
            reconnecting: true,
            subscribe: vi.fn(),
        })

        render(<ConnectionBanner />)
        expect(screen.getByText('connection.reconnecting')).toBeInTheDocument()
    })

    it('has role="alert" for accessibility', () => {
        mockedUseRealtime.mockReturnValue({
            connected: false,
            reconnecting: false,
            subscribe: vi.fn(),
        })

        render(<ConnectionBanner />)
        expect(screen.getByRole('alert')).toBeInTheDocument()
    })
})
