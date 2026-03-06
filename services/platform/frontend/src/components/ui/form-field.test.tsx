import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FormField } from './form-field'

describe('FormField', () => {
  it('renders label and input', () => {
    render(<FormField label="Username" />)
    const label = screen.getByText('Username')
    expect(label).toBeInTheDocument()
    const input = screen.getByRole('textbox')
    expect(input).toBeInTheDocument()
  })

  it('associates label with input via htmlFor/id', () => {
    render(<FormField label="Username" id="test-input" />)
    const label = screen.getByText('Username') as HTMLLabelElement
    expect(label.htmlFor).toBe('test-input')
    const input = screen.getByRole('textbox') as HTMLInputElement
    expect(input.id).toBe('test-input')
  })

  it('shows error message when touched and error provided', () => {
    render(<FormField label="Username" touched error="Username is required" />)
    expect(screen.getByText('Username is required')).toBeInTheDocument()
  })

  it('does not show error when not touched', () => {
    render(<FormField label="Username" touched={false} error="Username is required" />)
    expect(screen.queryByText('Username is required')).not.toBeInTheDocument()
  })

  it('does not show error when error is undefined', () => {
    render(<FormField label="Username" touched error={undefined} />)
    const input = screen.getByRole('textbox')
    expect(input).not.toHaveAttribute('aria-invalid')
  })

  it('shows required asterisk when required', () => {
    render(<FormField label="Username" required />)
    const asterisk = screen.getByText('*')
    expect(asterisk).toBeInTheDocument()
    expect(asterisk).toHaveAttribute('aria-hidden', 'true')
  })

  it('does not show required asterisk when not required', () => {
    render(<FormField label="Username" />)
    const asterisks = screen.queryAllByText('*')
    expect(asterisks).toHaveLength(0)
  })

  it('applies error styling to input when error shown', () => {
    render(<FormField label="Username" touched error="Username is required" />)
    const input = screen.getByRole('textbox')
    const inputClasses = input.className
    expect(inputClasses).toContain('border-destructive')
  })

  it('does not apply error styling when error not shown', () => {
    render(<FormField label="Username" touched={false} error="Username is required" />)
    const input = screen.getByRole('textbox')
    const inputClasses = input.className
    expect(inputClasses).not.toContain('border-destructive')
  })

  it('shows hint text when provided', () => {
    render(<FormField label="Username" hint="Enter your username" />)
    expect(screen.getByText('Enter your username')).toBeInTheDocument()
  })

  it('hides hint when error is shown', () => {
    render(<FormField label="Username" touched error="Username is required" hint="Enter your username" />)
    expect(screen.queryByText('Enter your username')).not.toBeInTheDocument()
    expect(screen.getByText('Username is required')).toBeInTheDocument()
  })

  it('sets aria-invalid when error shown', () => {
    render(<FormField label="Username" touched error="Username is required" />)
    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('does not set aria-invalid when error not shown', () => {
    render(<FormField label="Username" touched={false} error="Username is required" />)
    const input = screen.getByRole('textbox')
    expect(input).not.toHaveAttribute('aria-invalid')
  })

  it('renders leading icon when provided', () => {
    render(<FormField label="Username" leadingIcon={<span data-testid="leading-icon">@</span>} />)
    expect(screen.getByTestId('leading-icon')).toBeInTheDocument()
  })

  it('does not render leading icon when not provided', () => {
    render(<FormField label="Username" />)
    expect(screen.queryByTestId('leading-icon')).not.toBeInTheDocument()
  })

  it('adds pl-10 class when leading icon is provided', () => {
    render(<FormField label="Username" leadingIcon={<span data-testid="leading-icon">@</span>} />)
    const input = screen.getByRole('textbox')
    expect(input.className).toContain('pl-10')
  })

  it('associates error message with aria-describedby', () => {
    render(<FormField label="Username" touched error="Username is required" />)
    const input = screen.getByRole('textbox')
    const errorId = `${input.id}-error`
    expect(input).toHaveAttribute('aria-describedby', errorId)
  })

  it('associates hint with aria-describedby', () => {
    render(<FormField label="Username" hint="Enter your username" />)
    const input = screen.getByRole('textbox')
    const hintId = `${input.id}-hint`
    expect(input).toHaveAttribute('aria-describedby', hintId)
  })

  it('associates both error and hint with aria-describedby when both shown', () => {
    render(<FormField label="Username" hint="Enter your username" id="test-id" />)
    const input = screen.getByRole('textbox')
    expect(input).toHaveAttribute('aria-describedby', 'test-id-hint')
  })

  it('forwards ref to input element', () => {
    const ref = { current: null }
    render(<FormField label="Username" ref={ref} />)
    expect(ref.current).toBeInstanceOf(HTMLInputElement)
  })

  it('applies custom className to input', () => {
    render(<FormField label="Username" className="custom-class" />)
    const input = screen.getByRole('textbox')
    expect(input.className).toContain('custom-class')
  })

  it('passes through input attributes', () => {
    render(<FormField label="Username" placeholder="Enter username" maxLength={20} autoFocus />)
    const input = screen.getByRole('textbox') as HTMLInputElement
    expect(input).toHaveAttribute('placeholder', 'Enter username')
    expect(input).toHaveAttribute('maxLength', '20')
    expect(input).toHaveFocus()
  })

  it('error message has role="alert"', () => {
    render(<FormField label="Username" touched error="Username is required" />)
    const alert = screen.getByRole('alert')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveTextContent('Username is required')
  })
})
