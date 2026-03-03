import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SearchInput } from './SearchInput'

describe('SearchInput', () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('renders with placeholder text', () => {
        render(
            <SearchInput
                value=""
                onChange={() => {}}
                placeholder="Search incidents..."
            />
        )
        expect(screen.getByPlaceholderText('Search incidents...')).toBeInTheDocument()
    })

    it('renders search icon', () => {
        const { container } = render(
            <SearchInput value="" onChange={() => {}} />
        )
        const svg = container.querySelector('svg')
        expect(svg).toBeInTheDocument()
    })

    it('updates input value on user input', () => {
        render(
            <SearchInput value="" onChange={() => {}} />
        )
        const input = screen.getByRole('textbox') as HTMLInputElement

        fireEvent.change(input, { target: { value: 'test' } })

        expect(input.value).toBe('test')
    })

    it('debounces onChange callback', () => {
        const onChange = vi.fn()
        render(
            <SearchInput
                value=""
                onChange={onChange}
                debounceMs={300}
            />
        )
        const input = screen.getByRole('textbox')

        fireEvent.change(input, { target: { value: 't' } })
        expect(onChange).not.toHaveBeenCalled()

        fireEvent.change(input, { target: { value: 'te' } })
        expect(onChange).not.toHaveBeenCalled()

        vi.advanceTimersByTime(300)

        expect(onChange).toHaveBeenCalledWith('te')
        expect(onChange).toHaveBeenCalledTimes(1)
    })

    it('cancels previous debounce when input changes rapidly', () => {
        const onChange = vi.fn()
        render(
            <SearchInput
                value=""
                onChange={onChange}
                debounceMs={300}
            />
        )
        const input = screen.getByRole('textbox')

        fireEvent.change(input, { target: { value: 'test' } })
        vi.advanceTimersByTime(150)

        fireEvent.change(input, { target: { value: 'testing' } })
        vi.advanceTimersByTime(150)

        expect(onChange).not.toHaveBeenCalled()

        vi.advanceTimersByTime(150)

        expect(onChange).toHaveBeenCalledWith('testing')
        expect(onChange).toHaveBeenCalledTimes(1)
    })

    it('shows clear button when value is not empty', () => {
        render(
            <SearchInput value="test" onChange={() => {}} />
        )
        expect(screen.getByLabelText('Clear search')).toBeInTheDocument()
    })

    it('hides clear button when value is empty', () => {
        render(
            <SearchInput value="" onChange={() => {}} />
        )
        expect(screen.queryByLabelText('Clear search')).not.toBeInTheDocument()
    })

    it('clears input and calls onChange when clear button is clicked', () => {
        const onChange = vi.fn()
        render(
            <SearchInput value="test" onChange={onChange} />
        )
        const clearButton = screen.getByLabelText('Clear search')

        fireEvent.click(clearButton)

        expect(onChange).toHaveBeenCalledWith('')
    })

    it('responds to external value changes', () => {
        const { rerender } = render(
            <SearchInput value="initial" onChange={() => {}} />
        )
        const input = screen.getByRole('textbox') as HTMLInputElement

        expect(input.value).toBe('initial')

        rerender(<SearchInput value="updated" onChange={() => {}} />)

        expect(input.value).toBe('updated')
    })

    it('applies custom className', () => {
        const { container } = render(
            <SearchInput
                value=""
                onChange={() => {}}
                className="custom-class"
            />
        )
        expect(container.querySelector('.custom-class')).toBeInTheDocument()
    })

    it('has correct focus ring styling', () => {
        render(
            <SearchInput value="" onChange={() => {}} />
        )
        const input = screen.getByRole('textbox')

        expect(input.className).toContain('focus:ring-2')
        expect(input.className).toContain('focus:ring-blue-500')
    })
})
