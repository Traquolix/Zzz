import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcut } from './useKeyboardShortcuts'

describe('useKeyboardShortcuts', () => {
    beforeEach(() => {
        // Clear any registered shortcuts before each test
        // This is a bit tricky since the registry is module-scoped
        // We'll fire key events to ensure cleanup happens
    })

    afterEach(() => {
        // Make sure the document doesn't have focus in any input
        document.body.focus()
    })

    it('fires handler on matching key press', () => {
        const handler = vi.fn()
        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)
    })

    it('does not fire when focus is in input (unless global: true)', () => {
        const handler = vi.fn()
        const input = document.createElement('input')
        document.body.appendChild(input)
        input.focus()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler,
                global: false,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).not.toHaveBeenCalled()

        document.body.removeChild(input)
    })

    it('fires global shortcuts even in inputs', () => {
        const handler = vi.fn()
        const input = document.createElement('input')
        document.body.appendChild(input)
        input.focus()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler,
                global: true,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)

        document.body.removeChild(input)
    })

    it('normalizes ctrl/meta for cross-platform', () => {
        const handler = vi.fn()
        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler,
            })
        )

        // Fire with metaKey instead of ctrlKey (Mac style)
        const event = new KeyboardEvent('keydown', {
            key: 'k',
            metaKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)
    })

    it('cleans up on unmount', () => {
        const handler = vi.fn()
        const { unmount } = renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler,
            })
        )

        const event1 = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event1)
        expect(handler).toHaveBeenCalledTimes(1)

        unmount()

        const event2 = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event2)
        expect(handler).toHaveBeenCalledTimes(1) // Still only 1 from before
    })

    it('Escape always fires regardless of input focus', () => {
        const handler = vi.fn()
        const input = document.createElement('input')
        document.body.appendChild(input)
        input.focus()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'Escape',
                handler,
                global: false,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'Escape',
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)

        document.body.removeChild(input)
    })

    it('supports multiple shortcuts', () => {
        const handler1 = vi.fn()
        const handler2 = vi.fn()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler: handler1,
            })
        )

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'shift+?',
                handler: handler2,
            })
        )

        const event1 = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event1)
        expect(handler1).toHaveBeenCalledTimes(1)
        expect(handler2).not.toHaveBeenCalled()

        const event2 = new KeyboardEvent('keydown', {
            key: '?',
            shiftKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event2)
        expect(handler2).toHaveBeenCalledTimes(1)
    })

    it('does not fire when focus is in textarea (unless global: true)', () => {
        const handler = vi.fn()
        const textarea = document.createElement('textarea')
        document.body.appendChild(textarea)
        textarea.focus()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+s',
                handler,
                global: false,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 's',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).not.toHaveBeenCalled()

        document.body.removeChild(textarea)
    })

    it('does not fire when focus is in contenteditable element (unless global: true)', () => {
        const handler = vi.fn()
        const div = document.createElement('div')
        div.setAttribute('contenteditable', 'true')
        document.body.appendChild(div)
        div.focus()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+b',
                handler,
                global: false,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'b',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).not.toHaveBeenCalled()

        document.body.removeChild(div)
    })

    it('supports alt modifier', () => {
        const handler = vi.fn()
        renderHook(() =>
            useKeyboardShortcut({
                combo: 'alt+a',
                handler,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'a',
            altKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)
    })

    it('supports shift modifier', () => {
        const handler = vi.fn()
        renderHook(() =>
            useKeyboardShortcut({
                combo: 'shift+enter',
                handler,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'Enter',
            shiftKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)
    })

    it('case-insensitive key matching', () => {
        const handler = vi.fn()
        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+K',
                handler,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler).toHaveBeenCalledTimes(1)
    })

    it('handles multiple handlers for same combo', () => {
        const handler1 = vi.fn()
        const handler2 = vi.fn()

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler: handler1,
            })
        )

        renderHook(() =>
            useKeyboardShortcut({
                combo: 'ctrl+k',
                handler: handler2,
            })
        )

        const event = new KeyboardEvent('keydown', {
            key: 'k',
            ctrlKey: true,
            bubbles: true,
        })
        document.dispatchEvent(event)

        expect(handler1).toHaveBeenCalledTimes(1)
        expect(handler2).toHaveBeenCalledTimes(1)
    })
})
