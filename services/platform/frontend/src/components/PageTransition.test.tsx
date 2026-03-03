import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { PageTransition } from './PageTransition'

// Mock components for testing
function TestLayout() {
    return (
        <div>
            <header>Test Header</header>
            <main>
                <PageTransition />
            </main>
        </div>
    )
}

function Page1() {
    return <div>Page 1 Content</div>
}

function Page2() {
    return <div>Page 2 Content</div>
}

describe('PageTransition', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    it('renders outlet content', () => {
        render(
            <MemoryRouter initialEntries={['/page1']}>
                <Routes>
                    <Route element={<TestLayout />}>
                        <Route path="/page1" element={<Page1 />} />
                        <Route path="/page2" element={<Page2 />} />
                    </Route>
                </Routes>
            </MemoryRouter>
        )

        expect(screen.getByText('Page 1 Content')).toBeInTheDocument()
    })

    it('has id="main-content" for skip-to-content link', () => {
        const { container } = render(
            <MemoryRouter initialEntries={['/page1']}>
                <Routes>
                    <Route element={<TestLayout />}>
                        <Route path="/page1" element={<Page1 />} />
                    </Route>
                </Routes>
            </MemoryRouter>
        )

        const mainContent = container.querySelector('[id="main-content"]')
        expect(mainContent).toHaveAttribute('id', 'main-content')
    })

    it('applies initial content correctly', () => {
        const { container } = render(
            <MemoryRouter initialEntries={['/page1']}>
                <Routes>
                    <Route element={<TestLayout />}>
                        <Route path="/page1" element={<Page1 />} />
                        <Route path="/page2" element={<Page2 />} />
                    </Route>
                </Routes>
            </MemoryRouter>
        )

        expect(screen.getByText('Page 1 Content')).toBeInTheDocument()

        const mainContent = container.querySelector('[id="main-content"]')
        expect(mainContent).toHaveClass('opacity-100')
    })
})
