import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Skeleton, TableSkeleton } from './Skeleton'

describe('Skeleton', () => {
    it('renders default single line', () => {
        const { container } = render(<Skeleton />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]')
        expect(lines).toHaveLength(1)
    })

    it('renders correct number of lines with lines prop', () => {
        const { container } = render(<Skeleton lines={5} />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]')
        expect(lines).toHaveLength(5)
    })


    it('applies custom className', () => {
        const { container } = render(<Skeleton className="custom-class" />)
        const wrapper = container.querySelector('.custom-class')
        expect(wrapper).toBeInTheDocument()
    })

    it('uses deterministic taper widths by default', () => {
        const { container } = render(<Skeleton lines={5} />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]') as NodeListOf<HTMLElement>
        const expectedWidths = [100, 95, 85, 70, 60]

        lines.forEach((line, index) => {
            const width = parseInt(line.style.width || '0')
            expect(width).toBe(expectedWidths[index])
        })
    })



    it('pattern="title" renders 2 lines with correct widths', () => {
        const { container } = render(<Skeleton pattern="title" />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]') as NodeListOf<HTMLElement>
        expect(lines).toHaveLength(2)
        expect(parseInt(lines[0].style.width || '0')).toBe(100)
        expect(parseInt(lines[1].style.width || '0')).toBe(60)
    })

    it('pattern="paragraph" renders 4 lines with correct widths', () => {
        const { container } = render(<Skeleton pattern="paragraph" />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]') as NodeListOf<HTMLElement>
        expect(lines).toHaveLength(4)
        expect(parseInt(lines[0].style.width || '0')).toBe(100)
        expect(parseInt(lines[1].style.width || '0')).toBe(95)
        expect(parseInt(lines[2].style.width || '0')).toBe(85)
        expect(parseInt(lines[3].style.width || '0')).toBe(70)
    })

    it('pattern="card" renders 5 lines with correct widths', () => {
        const { container } = render(<Skeleton pattern="card" />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]') as NodeListOf<HTMLElement>
        expect(lines).toHaveLength(5)
        expect(parseInt(lines[0].style.width || '0')).toBe(60)
        expect(parseInt(lines[1].style.width || '0')).toBe(100)
        expect(parseInt(lines[2].style.width || '0')).toBe(100)
        expect(parseInt(lines[3].style.width || '0')).toBe(90)
        expect(parseInt(lines[4].style.width || '0')).toBe(75)
    })
})

describe('TableSkeleton', () => {
    it('renders default rows and columns', () => {
        const { container } = render(<TableSkeleton />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]')
        expect(lines).toHaveLength(5 * 4) // 5 rows * 4 columns
    })

    it('renders correct number of rows and columns', () => {
        const { container } = render(<TableSkeleton rows={3} cols={6} />)
        const lines = container.querySelectorAll('[class*="animate-pulse"]')
        expect(lines).toHaveLength(3 * 6)
    })





})
