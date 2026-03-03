import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedSync } from './useDebouncedSync'

describe('useDebouncedSync', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces callback with default delay (500ms)', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback))

    act(() => {
      result.current()
    })

    // Callback should not be called immediately
    expect(callback).not.toHaveBeenCalled()

    // Callback should not be called before delay
    act(() => {
      vi.advanceTimersByTime(400)
    })
    expect(callback).not.toHaveBeenCalled()

    // Callback should be called after delay
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('debounces callback with custom delay', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 200))

    act(() => {
      result.current()
    })

    // Callback should not be called before custom delay
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(callback).not.toHaveBeenCalled()

    // Callback should be called after custom delay
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('resets delay on rapid calls', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 200))

    // First call
    act(() => {
      result.current()
    })

    // Second call before delay (should reset)
    act(() => {
      vi.advanceTimersByTime(100)
      result.current()
    })

    // Third call before delay (should reset again)
    act(() => {
      vi.advanceTimersByTime(100)
      result.current()
    })

    // Callback should not have been called yet
    expect(callback).not.toHaveBeenCalled()

    // After additional delay, callback should fire only once (last call)
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('only fires the last callback when called rapidly', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 100))

    // Multiple rapid calls
    act(() => {
      result.current('call1')
      result.current('call2')
      result.current('call3')
    })

    expect(callback).not.toHaveBeenCalled()

    // After delay, callback should fire once with last arguments
    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback).toHaveBeenCalledWith('call3')
  })

  it('passes arguments to the callback', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 100))

    act(() => {
      result.current('arg1', 'arg2', 123)
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(callback).toHaveBeenCalledWith('arg1', 'arg2', 123)
  })

  it('updates callback reference when dependency changes', () => {
    const callback1 = vi.fn()
    const callback2 = vi.fn()

    const { result, rerender } = renderHook(
      ({ cb, delay }: { cb: (...args: any[]) => void; delay: number }) =>
        useDebouncedSync(cb, delay),
      {
        initialProps: { cb: callback1, delay: 100 },
      }
    )

    act(() => {
      result.current()
    })

    // Change callback while waiting
    rerender({ cb: callback2, delay: 100 })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    // callback2 should be called, not callback1
    expect(callback1).not.toHaveBeenCalled()
    expect(callback2).toHaveBeenCalledTimes(1)
  })

  it('cleans up timeout on unmount', () => {
    const callback = vi.fn()
    const { result, unmount } = renderHook(() => useDebouncedSync(callback, 100))

    act(() => {
      result.current()
    })

    // Unmount before delay expires
    unmount()

    // Advance timers past the delay
    act(() => {
      vi.advanceTimersByTime(100)
    })

    // Callback should not fire because timeout was cleared
    expect(callback).not.toHaveBeenCalled()
  })

  it('clears previous timeout when called again', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 100))

    act(() => {
      result.current('first')
    })

    act(() => {
      vi.advanceTimersByTime(50)
    })

    act(() => {
      result.current('second')
    })

    // Should not call yet
    expect(callback).not.toHaveBeenCalled()

    // After 50 more ms (100 total from first call), still no call
    act(() => {
      vi.advanceTimersByTime(50)
    })
    expect(callback).not.toHaveBeenCalled()

    // After 100 more ms (total 150, but only 100 from second call), callback fires
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback).toHaveBeenCalledWith('second')
  })

  it('handles zero delay', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 0))

    act(() => {
      result.current()
    })

    // Should be called on next tick (0ms delay)
    act(() => {
      vi.advanceTimersByTime(0)
    })

    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('works with multiple sequential debounce calls', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedSync(callback, 100))

    // First debounce sequence
    act(() => {
      result.current('a')
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback).toHaveBeenCalledWith('a')

    // Second debounce sequence
    act(() => {
      result.current('b')
    })

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(callback).toHaveBeenCalledTimes(2)
    expect(callback).toHaveBeenLastCalledWith('b')
  })

  it('handles callback that throws', () => {
    const callback = vi.fn(() => {
      throw new Error('Callback error')
    })

    const { result } = renderHook(() => useDebouncedSync(callback, 100))

    act(() => {
      result.current()
    })

    // Should throw when debounce fires
    expect(() => {
      act(() => {
        vi.advanceTimersByTime(100)
      })
    }).toThrow('Callback error')
  })

  it('returns the same debounced function instance', () => {
    const callback = vi.fn()
    const { result, rerender } = renderHook(() => useDebouncedSync(callback, 100))

    const firstInstance = result.current

    rerender()

    const secondInstance = result.current

    // They should be the same function
    expect(firstInstance).toBe(secondInstance)
  })
})
