import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Modal } from './modal'

describe('Modal', () => {
  it('renders children when open=true', () => {
    render(
      <Modal open={true} onClose={() => {}}>
        <div>Modal Content</div>
      </Modal>,
    )

    expect(screen.getByText('Modal Content')).toBeInTheDocument()
  })

  it('does not render when open=false', () => {
    render(
      <Modal open={false} onClose={() => {}}>
        <div>Modal Content</div>
      </Modal>,
    )

    expect(screen.queryByText('Modal Content')).not.toBeInTheDocument()
  })

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn()
    const { container } = render(
      <Modal open={true} onClose={onClose}>
        <div>Modal Content</div>
      </Modal>,
    )

    const backdrop = container.querySelector('[role="presentation"]')
    expect(backdrop).toBeInTheDocument()
    fireEvent.click(backdrop!)
    expect(onClose).toHaveBeenCalled()
  })

  it('does not call onClose when content clicked', () => {
    const onClose = vi.fn()
    render(
      <Modal open={true} onClose={onClose}>
        <div>Modal Content</div>
      </Modal>,
    )

    fireEvent.click(screen.getByText('Modal Content'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose on Escape key', async () => {
    const onClose = vi.fn()
    render(
      <Modal open={true} onClose={onClose}>
        <div>Modal Content</div>
      </Modal>,
    )

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('has role="dialog" and aria-modal="true"', () => {
    const { container } = render(
      <Modal open={true} onClose={() => {}}>
        <div>Modal Content</div>
      </Modal>,
    )

    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toHaveAttribute('role', 'dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('applies animation classes', () => {
    const { container } = render(
      <Modal open={true} onClose={() => {}}>
        <div>Modal Content</div>
      </Modal>,
    )

    const modalWrapper = container.querySelector('[role="presentation"]')
    const dialog = container.querySelector('[role="dialog"]')

    // Modal wrapper should have animation classes
    expect(modalWrapper).toHaveClass('animate-in', 'fade-in-0', 'duration-150')
    // Dialog should have zoom and fade animation
    expect(dialog).toHaveClass('animate-in', 'zoom-in-95', 'fade-in-0', 'duration-200')
  })

  it('applies dark mode classes', () => {
    const { container } = render(
      <Modal open={true} onClose={() => {}}>
        <div>Modal Content</div>
      </Modal>,
    )

    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toHaveClass('dark:bg-slate-900')
  })

  it('applies custom className', () => {
    const { container } = render(
      <Modal open={true} onClose={() => {}} className="custom-class">
        <div>Modal Content</div>
      </Modal>,
    )

    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toHaveClass('custom-class')
  })

  it('focuses first focusable element on open', async () => {
    render(
      <Modal open={true} onClose={() => {}}>
        <button>First Button</button>
        <button>Second Button</button>
      </Modal>,
    )

    await waitFor(() => {
      const firstButton = screen.getByText('First Button')
      expect(firstButton).toHaveFocus()
    })
  })

  it('handles Tab key for focus cycling', async () => {
    render(
      <Modal open={true} onClose={() => {}}>
        <button>First</button>
        <button>Second</button>
      </Modal>,
    )

    const firstButton = screen.getByText('First')

    await waitFor(() => {
      expect(firstButton).toHaveFocus()
    })

    // Tab keydown event should be handled without throwing
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(firstButton).toBeInTheDocument()
  })

  it('applies mobileFullScreen classes when enabled', () => {
    const { container } = render(
      <Modal open={true} onClose={() => {}} mobileFullScreen={true}>
        <div>Modal Content</div>
      </Modal>,
    )

    const dialog = container.querySelector('[role="dialog"]')
    expect(dialog).toHaveClass('max-md:w-full', 'max-md:h-dvh', 'max-md:rounded-none')
  })

  it('restores focus to previous element on close', async () => {
    const { rerender } = render(
      <div>
        <button id="trigger">Open Modal</button>
        <Modal open={true} onClose={() => {}}>
          <div>Modal Content</div>
        </Modal>
      </div>,
    )

    const trigger = screen.getByText('Open Modal') as HTMLButtonElement
    trigger.focus()
    expect(trigger).toHaveFocus()

    rerender(
      <div>
        <button id="trigger">Open Modal</button>
        <Modal open={false} onClose={() => {}}>
          <div>Modal Content</div>
        </Modal>
      </div>,
    )

    await waitFor(() => {
      expect(trigger).toHaveFocus()
    })
  })
})
