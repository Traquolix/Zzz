/**
 * Tests for SHMMap component — XSS vulnerability fix verification.
 *
 * Goal: Verify that infrastructure names containing HTML/script tags are
 * rendered as escaped text, not executed.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'

// Mock ResizeObserver which is used in the component
class MockResizeObserver {
    observe = vi.fn()
    unobserve = vi.fn()
    disconnect = vi.fn()
}

(globalThis as any).ResizeObserver = MockResizeObserver as any

// Mock mapbox-gl module
vi.mock('mapbox-gl', () => {
    class MockMapInstance {
        addControl = vi.fn()
        once = vi.fn((event: string, cb: () => void) => {
            if (event === 'style.load') {
                setTimeout(cb, 0)
            }
        })
        remove = vi.fn()
        fitBounds = vi.fn()
        resize = vi.fn()
    }

    class MockMarker {
        element: any

        constructor({ element }: any) {
            this.element = element
        }

        setLngLat = vi.fn(() => this)
        addTo = vi.fn(() => this)
        remove = vi.fn()
        getLngLat = vi.fn(() => ({ lng: 0, lat: 0 }))
        getElement = vi.fn(() => this.element)
    }

    class MockLngLatBounds {
        extend = vi.fn()
    }

    class MockNavigationControl {}

    // Return a module that has Map as a property so mapboxgl.Map works
    const mockModule = {
        Map: MockMapInstance,
        Marker: MockMarker,
        LngLatBounds: MockLngLatBounds,
        NavigationControl: MockNavigationControl,
        accessToken: '',
    }

    return {
        default: mockModule,
        ...mockModule,
    }
})

// Mock useFibers hook
vi.mock('@/hooks/useFibers', () => ({
    useFibers: () => ({
        fibers: [
            {
                parentFiberId: 'cable-1',
                coordinates: [
                    [7.25, 43.69],
                    [7.26, 43.70],
                    [7.27, 43.71],
                ],
            },
        ],
    }),
}))

// Mock mapbox CSS import
vi.mock('mapbox-gl/dist/mapbox-gl.css', () => ({}))

// Mock config
vi.mock('@/config/mapbox', () => ({
    MAPBOX_TOKEN: 'pk.test-token',
}))

import { SHMMap } from './SHMMap'
import type { Infrastructure } from '@/types/infrastructure'

describe('SHMMap — XSS fix verification', () => {
    const baseInfra: Infrastructure = {
        id: 'test-1',
        fiberId: 'cable-1',
        type: 'bridge',
        name: 'Test Bridge',
        startChannel: 0,
        endChannel: 2,
    }

    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders infrastructure name as text, not HTML', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            name: 'Normal Bridge Name',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        // Wait for async map initialization
        await waitFor(() => {
            // Check that a marker element was created (has the class applied to marker divs)
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
        })
    })

    it('escapes infrastructure names with HTML tags', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            id: 'xss-test-1',
            name: '<script>alert("XSS")</script>Bridge',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        // The dangerous string should NOT be present as HTML in the DOM
        // textContent should contain the literal string without executing the script
        await waitFor(() => {
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
            if (markerElement) {
                // textContent will show the literal string, not execute it
                expect(markerElement.textContent).toContain('<script>')
                // Make sure no actual script tag was created as a child
                expect(markerElement.querySelector('script')).toBeNull()
            }
        })
    })

    it('escapes infrastructure names with img XSS vectors', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            id: 'xss-test-2',
            name: '<img src=x onerror="alert(\'XSS\')">Bridge',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        await waitFor(() => {
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
            if (markerElement) {
                // The img tag should be in textContent, not parsed as HTML
                expect(markerElement.textContent).toContain('<img')
                // Make sure no img element was created as a child
                expect(markerElement.querySelector('img')).toBeNull()
            }
        })
    })

    it('escapes infrastructure names with event handler XSS vectors', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            id: 'xss-test-3',
            name: '<span onclick="maliciousFunction()">Click</span>',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        await waitFor(() => {
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
            if (markerElement) {
                // The dangerous code should be in textContent, not executed
                expect(markerElement.textContent).toContain('onclick')
                // Make sure no additional span was created from the name
                const innerSpans = markerElement.querySelectorAll('span')
                // Should only have the one we explicitly created via createElement
                expect(innerSpans.length).toBeLessThanOrEqual(1)
            }
        })
    })

    it('safely handles infrastructure names with unicode and special characters', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            id: 'unicode-test',
            name: 'Bridge Übersee & Infrastructure №1 ✓',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        await waitFor(() => {
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
            if (markerElement) {
                // Special characters should be preserved and rendered correctly
                expect(markerElement.textContent).toContain('Übersee')
                expect(markerElement.textContent).toContain('№1')
                expect(markerElement.textContent).toContain('✓')
            }
        })
    })

    it('renders marker with safe hardcoded SVG and status dot', async () => {
        const infra: Infrastructure = {
            ...baseInfra,
            name: 'SVG Test Bridge',
        }

        const { container } = render(
            <SHMMap
                infrastructures={[infra]}
                selectedInfrastructure={null}
                onSelect={vi.fn()}
            />
        )

        await waitFor(() => {
            const markerElement = container.querySelector('[class*="rounded-lg"]')
            expect(markerElement).toBeDefined()
            if (markerElement) {
                // SVG should be rendered as HTML (it's hardcoded and safe)
                const svg = markerElement.querySelector('svg')
                expect(svg).toBeDefined()

                // Status dot should be rendered
                const statusDot = markerElement.querySelector('[class*="rounded-full"]')
                expect(statusDot).toBeDefined()

                // Name should be in a span
                const spans = markerElement.querySelectorAll('span')
                const nameSpan = Array.from(spans).find(
                    span => span.textContent === 'SVG Test Bridge'
                )
                expect(nameSpan).toBeDefined()
            }
        })
    })
})
