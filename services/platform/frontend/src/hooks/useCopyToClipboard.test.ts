import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCopyToClipboard } from './useCopyToClipboard'

describe('useCopyToClipboard', () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('copies text to clipboard', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue(undefined) }
        })

        const { result } = renderHook(() => useCopyToClipboard())
        const testText = 'test content'

        await act(async () => {
            const success = await result.current.copy(testText)
            expect(success).toBe(true)
        })

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith(testText)
    })

    it('sets copied to true after copy', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue(undefined) }
        })

        const { result } = renderHook(() => useCopyToClipboard())

        expect(result.current.copied).toBe(false)

        await act(async () => {
            await result.current.copy('text')
        })

        expect(result.current.copied).toBe(true)
    })

    it('resets copied after delay', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue(undefined) }
        })

        const { result } = renderHook(() => useCopyToClipboard(1000))

        await act(async () => {
            await result.current.copy('text')
        })

        expect(result.current.copied).toBe(true)

        act(() => {
            vi.advanceTimersByTime(1000)
        })

        expect(result.current.copied).toBe(false)
    })

    it('handles custom reset delay', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue(undefined) }
        })

        const customDelay = 3000
        const { result } = renderHook(() => useCopyToClipboard(customDelay))

        await act(async () => {
            await result.current.copy('text')
        })

        expect(result.current.copied).toBe(true)

        act(() => {
            vi.advanceTimersByTime(customDelay - 1)
        })
        expect(result.current.copied).toBe(true)

        act(() => {
            vi.advanceTimersByTime(1)
        })
        expect(result.current.copied).toBe(false)
    })

    it('handles clipboard API failure gracefully', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockRejectedValue(new Error('API failed')) }
        })

        // Mock document.execCommand as well
        const originalExecCommand = document.execCommand
        document.execCommand = vi.fn().mockReturnValue(true)

        try {
            const { result } = renderHook(() => useCopyToClipboard())

            let success = false
            await act(async () => {
                success = await result.current.copy('text')
            })

            expect(success).toBe(true) // Falls back to document.execCommand
        } finally {
            document.execCommand = originalExecCommand
        }
    })

    it('clears previous timeout when copying again', async () => {
        Object.assign(navigator, {
            clipboard: { writeText: vi.fn().mockResolvedValue(undefined) }
        })

        const { result } = renderHook(() => useCopyToClipboard(1000))

        await act(async () => {
            await result.current.copy('text1')
        })

        act(() => {
            vi.advanceTimersByTime(500)
        })

        expect(result.current.copied).toBe(true)

        await act(async () => {
            await result.current.copy('text2')
        })

        act(() => {
            vi.advanceTimersByTime(500)
        })

        expect(result.current.copied).toBe(true)

        act(() => {
            vi.advanceTimersByTime(500)
        })

        expect(result.current.copied).toBe(false)
    })
})
