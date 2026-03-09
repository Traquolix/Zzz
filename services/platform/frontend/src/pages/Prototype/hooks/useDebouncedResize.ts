import { useRef, useState, useEffect, useCallback, type RefObject } from 'react'

/**
 * Debounced ResizeObserver hook.
 *
 * Returns a stable `width` that only updates once the observed element has
 * stopped resizing for `delay` ms.  This prevents charts from re-rendering
 * on every animation frame during CSS width transitions.
 *
 * Also returns a `settled` boolean that is `false` while a resize is
 * in-flight and flips to `true` once the debounce fires — callers can use
 * this to skip expensive work during the transition.
 */
export function useDebouncedResize(
  ref: RefObject<HTMLElement | null>,
  delay = 200,
): { width: number; settled: boolean } {
  const [width, setWidth] = useState(0)
  const [settled, setSettled] = useState(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleResize = useCallback(
    (entries: ResizeObserverEntry[]) => {
      const w = entries[0]?.contentRect.width ?? 0
      if (w === 0) return

      setSettled(false)

      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        setWidth(w)
        setSettled(true)
      }, delay)
    },
    [delay],
  )

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Seed initial width synchronously
    if (el.clientWidth > 0) setWidth(el.clientWidth)

    const observer = new ResizeObserver(handleResize)
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [ref, handleResize])

  return { width, settled }
}
