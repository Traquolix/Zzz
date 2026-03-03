import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { Breadcrumb } from './breadcrumb'

describe('Breadcrumb', () => {
    it('renders nothing when only 1 item', () => {
        const { container } = render(
            <BrowserRouter>
                <Breadcrumb items={[{ label: 'Dashboard' }]} />
            </BrowserRouter>
        )
        expect(container.querySelector('nav')).not.toBeInTheDocument()
    })

    it('renders all items with separators', () => {
        const { container } = render(
            <BrowserRouter>
                <Breadcrumb
                    items={[
                        { label: 'Dashboard', href: '/' },
                        { label: 'Incidents' },
                    ]}
                />
            </BrowserRouter>
        )
        expect(screen.getByText('Dashboard')).toBeInTheDocument()
        expect(screen.getByText('Incidents')).toBeInTheDocument()

        // Check for separator (ChevronRight) - look for SVG with aria-hidden
        const separators = container.querySelectorAll('svg[aria-hidden="true"]')
        expect(separators.length).toBeGreaterThan(0)
    })

    it('current page is non-clickable with aria-current="page"', () => {
        render(
            <BrowserRouter>
                <Breadcrumb
                    items={[
                        { label: 'Dashboard', href: '/' },
                        { label: 'Incidents' },
                    ]}
                />
            </BrowserRouter>
        )
        const currentPage = screen.getByText('Incidents')
        expect(currentPage).toHaveAttribute('aria-current', 'page')
        expect(currentPage.tagName).toBe('SPAN')
    })

    it('links are clickable', () => {
        render(
            <BrowserRouter>
                <Breadcrumb
                    items={[
                        { label: 'Dashboard', href: '/' },
                        { label: 'Incidents' },
                    ]}
                />
            </BrowserRouter>
        )
        const link = screen.getByRole('link', { name: 'Dashboard' })
        expect(link).toBeInTheDocument()
        expect(link).toHaveAttribute('href', '/')
    })

    it('has aria-label="Breadcrumb" on nav', () => {
        render(
            <BrowserRouter>
                <Breadcrumb
                    items={[
                        { label: 'Dashboard', href: '/' },
                        { label: 'Incidents' },
                    ]}
                />
            </BrowserRouter>
        )
        const nav = screen.getByRole('navigation', { name: 'Breadcrumb' })
        expect(nav).toBeInTheDocument()
    })
})
