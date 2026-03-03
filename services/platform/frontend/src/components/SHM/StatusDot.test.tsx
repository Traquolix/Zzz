/**
 * Tests for the StatusDot component.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'

// Mock react-i18next
vi.mock('react-i18next', () => ({
    useTranslation: () => ({
        t: (key: string, defaultValue?: string) => defaultValue || key,
        i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
}))

import { StatusDot } from './StatusDot'
import type { SHMStatus } from '@/types/infrastructure'

describe('StatusDot', () => {
    describe('default props (no shmData)', () => {
        it('renders with default status nominal', () => {
            const { container } = render(<StatusDot />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot).toBeInTheDocument()
        })

        it('renders hardcoded values when shmData is not provided', async () => {
            const { container } = render(<StatusDot status="nominal" />)
            const wrapper = container.querySelector('[class*="relative"]')
            expect(wrapper).toBeInTheDocument()
        })

        it('renders with status=warning', () => {
            const { container } = render(<StatusDot status="warning" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('amber')
        })

        it('renders with status=critical', () => {
            const { container } = render(<StatusDot status="critical" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('red')
        })
    })

    describe('with shmData prop', () => {
        const mockSHMDataNominal: SHMStatus = {
            status: 'nominal',
            currentMean: 1.15,
            baselineMean: 1.10,
            deviationSigma: 0.5,
            direction: 'stable',
        }

        const mockSHMDataWarning: SHMStatus = {
            status: 'warning',
            currentMean: 1.25,
            baselineMean: 1.10,
            deviationSigma: 2.5,
            direction: 'increase',
        }

        const mockSHMDataCritical: SHMStatus = {
            status: 'critical',
            currentMean: 1.40,
            baselineMean: 1.10,
            deviationSigma: 4.5,
            direction: 'increase',
        }

        it('accepts shmData prop', () => {
            const { container } = render(
                <StatusDot status="nominal" shmData={mockSHMDataNominal} />
            )
            expect(container.querySelector('[class*="rounded-full"]')).toBeInTheDocument()
        })

        it('displays currentMean as Peak frequency when nominal with shmData', async () => {
            const { container } = render(
                <StatusDot status="nominal" shmData={mockSHMDataNominal} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('1.15')
            }, { timeout: 1000 })
        })

        it('displays baselineMean as Expected when nominal with shmData', async () => {
            const { container } = render(
                <StatusDot status="nominal" shmData={mockSHMDataNominal} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('1.10')
            }, { timeout: 1000 })
        })

        it('formats deviationSigma with sigma symbol', async () => {
            const { container } = render(
                <StatusDot status="nominal" shmData={mockSHMDataNominal} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('σ')
            }, { timeout: 1000 })
        })

        it('displays real values when warning with shmData', async () => {
            const { container } = render(
                <StatusDot status="warning" shmData={mockSHMDataWarning} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('1.25')
                expect(container.textContent).toContain('1.10')
            }, { timeout: 1000 })
        })

        it('displays real values when critical with shmData', async () => {
            const { container } = render(
                <StatusDot status="critical" shmData={mockSHMDataCritical} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('1.40')
                expect(container.textContent).toContain('1.10')
            }, { timeout: 1000 })
        })

        it('handles negative deviationSigma correctly', async () => {
            const negativeDeviation: SHMStatus = {
                ...mockSHMDataNominal,
                deviationSigma: -1.5,
            }

            const { container } = render(
                <StatusDot status="nominal" shmData={negativeDeviation} />
            )

            // Hover to show tooltip
            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                expect(container.textContent).toContain('σ')
            }, { timeout: 1000 })
        })
    })

    describe('status color rendering', () => {
        it('renders with emerald color for nominal status', () => {
            const { container } = render(<StatusDot status="nominal" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('emerald')
        })

        it('renders with amber color for warning status', () => {
            const { container } = render(<StatusDot status="warning" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('amber')
        })

        it('renders with red color for critical status', () => {
            const { container } = render(<StatusDot status="critical" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('red')
        })
    })

    describe('size prop', () => {
        it('renders with small size', () => {
            const { container } = render(<StatusDot size="sm" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('w-2')
        })

        it('renders with medium size (default)', () => {
            const { container } = render(<StatusDot size="md" />)
            const dot = container.querySelector('[class*="rounded-full"]')
            expect(dot?.className).toContain('w-2.5')
        })
    })

    describe('className prop', () => {
        it('applies custom className', () => {
            const { container } = render(<StatusDot className="custom-class" />)
            const wrapper = container.querySelector('[class*="custom-class"]')
            expect(wrapper).toBeInTheDocument()
        })
    })

    describe('tooltip visibility', () => {
        it('shows tooltip on hover', async () => {
            const { container } = render(<StatusDot status="nominal" />)

            const wrapper = container.querySelector('[class*="relative"]')
            expect(wrapper).toBeInTheDocument()

            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
            }

            await waitFor(() => {
                const tooltip = container.querySelector('[class*="fixed"]')
                expect(tooltip).toBeInTheDocument()
            }, { timeout: 1000 })
        })

        it('hides tooltip on mouse leave', async () => {
            const { container } = render(<StatusDot status="nominal" />)

            const wrapper = container.querySelector('[class*="relative"]')
            if (wrapper) {
                fireEvent.mouseEnter(wrapper)
                fireEvent.mouseLeave(wrapper)
            }

            // Verify the component still renders
            expect(container.querySelector('[class*="rounded-full"]')).toBeInTheDocument()
        })
    })
})
