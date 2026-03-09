import { useState, useEffect } from 'react'

/** Read the actual computed width of the sidebar DOM element. */
export function getSidebarWidth(): number {
  return document.querySelector<HTMLElement>('.proto-sidebar')?.offsetWidth ?? 0
}

/**
 * Reactively tracks the sidebar's computed pixel width via ResizeObserver.
 * Returns 0 when the sidebar is hidden/absent.
 */
export function useSidebarWidth(): number {
  const [width, setWidth] = useState(getSidebarWidth)

  useEffect(() => {
    const el = document.querySelector<HTMLElement>('.proto-sidebar')
    if (!el) return

    setWidth(el.offsetWidth)
    const observer = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? 0
      setWidth(w)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return width
}
