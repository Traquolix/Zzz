import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Button } from './button'

describe('Button', () => {
  it('renders normally by default', () => {
    render(<Button>Click me</Button>)
    const button = screen.getByRole('button', { name: 'Click me' })
    expect(button).toBeInTheDocument()
    expect(button).not.toHaveAttribute('disabled')
    expect(button).toHaveAttribute('aria-busy', 'false')
  })

  it('shows spinner when isLoading=true', () => {
    const { container: _container } = render(<Button isLoading>Click me</Button>)
    const spinner = _container.querySelector('svg[class*="animate-spin"]')
    expect(spinner).toBeInTheDocument()
  })

  it('disables button when isLoading=true', () => {
    render(<Button isLoading>Click me</Button>)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('disabled')
  })

  it('shows loadingText when provided with isLoading=true', () => {
    render(<Button isLoading loadingText="Loading...">Click me</Button>)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('hides children when loadingText provided and isLoading=true', () => {
    render(<Button isLoading loadingText="Loading...">Click me</Button>)
    expect(screen.queryByText('Click me')).not.toBeInTheDocument()
  })

  it('adds aria-busy when loading', () => {
    render(<Button isLoading>Click me</Button>)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('does not show spinner when isLoading=false', () => {
    const { container: _container } = render(<Button isLoading={false}>Click me</Button>)
    const spinner = _container.querySelector('svg[class*="animate-spin"]')
    expect(spinner).not.toBeInTheDocument()
  })
})
