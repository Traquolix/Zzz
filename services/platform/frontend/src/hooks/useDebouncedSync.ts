import { useCallback, useRef, useEffect } from 'react'

/**
 * Hook that provides a debounced callback function.
 * Useful for syncing state to server without triggering too many requests.
 *
 * @param callback - The function to call after debounce delay
 * @param delay - Debounce delay in milliseconds (default: 500ms)
 * @returns A debounced version of the callback
 */
export function useDebouncedSync<T extends (...args: Parameters<T>) => void>(
    callback: T,
    delay = 500
): T {
    const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const callbackRef = useRef(callback)

    // Keep callback ref up to date
    useEffect(() => {
        callbackRef.current = callback
    }, [callback])

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (timeoutRef.current) {
                clearTimeout(timeoutRef.current)
            }
        }
    }, [])

    const debouncedCallback = useCallback((...args: Parameters<T>) => {
        if (timeoutRef.current) {
            clearTimeout(timeoutRef.current)
        }
        timeoutRef.current = setTimeout(() => {
            callbackRef.current(...args)
        }, delay)
    }, [delay]) as T

    return debouncedCallback
}
