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
  const latestWidthRef = useRef(0)
  const initialised = useRef(false)
  const firstObservation = useRef(true)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    // Seed initial width synchronously (no transition flag on first mount).
    // When clientWidth is 0 (e.g. container-type containment, pending layout),
    // retry on next animation frame so the element has been laid out.
    let rafId: number | null = null
    if (!initialised.current) {
      if (el.clientWidth > 0) {
        setWidth(el.clientWidth)
        latestWidthRef.current = el.clientWidth
        initialised.current = true
      } else {
        rafId = requestAnimationFrame(() => {
          if (!initialised.current && el.clientWidth > 0) {
            setWidth(el.clientWidth)
            latestWidthRef.current = el.clientWidth
            initialised.current = true
          }
        })
      }
    }

    const observer = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? 0
      if (w <= 0) return

      latestWidthRef.current = w

      // First observation — seed without marking as transitioning.
      // Cancel any pending RAF to avoid a redundant render.
      if (firstObservation.current) {
        firstObservation.current = false
        if (rafId !== null) {
          cancelAnimationFrame(rafId)
          rafId = null
        }
        initialised.current = true
        setWidth(w)
        return
      }

      setTransitioning(true)

      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        // Always use the most recent width, not the closure-captured value
        setWidth(latestWidthRef.current)
        setTransitioning(false)
      }, delay)
    })
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (timerRef.current) clearTimeout(timerRef.current)
      if (rafId !== null) cancelAnimationFrame(rafId)
    }
    // ref identity is stable across renders; only delay matters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [delay])

  return { width, transitioning }
}
