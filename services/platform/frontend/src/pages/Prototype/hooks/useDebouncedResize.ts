import { useRef, useState, useEffect, type RefObject } from 'react'

/**
 * Tracks the width of a DOM element via ResizeObserver.
 *
 * During rapid resize sequences (e.g. CSS width transitions), `transitioning`
 * is `true` and `width` holds its stale value. Once the element stops resizing
 * for `delay` ms, `transitioning` flips to `false` and `width` updates to the
 * final value. Consumers can swap in a skeleton while `transitioning` is true.
 */
export function useDebouncedResize(
  ref: RefObject<HTMLElement | null>,
  delay = 250,
): { width: number; transitioning: boolean } {
  const [width, setWidth] = useState(0)
  const [transitioning, setTransitioning] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const initialised = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Seed initial width synchronously (no transition flag on first mount)
    if (el.clientWidth > 0 && !initialised.current) {
      setWidth(el.clientWidth)
      initialised.current = true
    }

    const observer = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? 0
      if (w <= 0) return

      // First observation — seed without marking as transitioning
      if (!initialised.current) {
        initialised.current = true
        setWidth(w)
        return
      }

      setTransitioning(true)

      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        setWidth(w)
        setTransitioning(false)
      }, delay)
    })
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (timerRef.current) clearTimeout(timerRef.current)
    }
    // ref identity is stable across renders; only delay matters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [delay])

  return { width, transitioning }
}
