import { createContext, useContext, useState, useEffect, type RefObject } from 'react'

/**
 * Context that holds a ref to the sidebar DOM element.
 * SidePanel provides this; consumers (Legend, etc.) use useSidebarWidth() to read the width.
 */
export const SidebarRefContext = createContext<RefObject<HTMLElement | null>>({ current: null })

/**
 * Read the current pixel width of the sidebar element from a ref.
 * Usable outside React (e.g. in imperative map callbacks).
 */
export function getSidebarWidth(ref: RefObject<HTMLElement | null>): number {
  return ref.current?.offsetWidth ?? 0
}

/**
 * Reactively tracks the sidebar's computed pixel width via ResizeObserver.
 * Reads the ref from SidebarRefContext (provided by SidePanel).
 * Returns 0 when the sidebar is hidden/absent.
 */
export function useSidebarWidth(): number {
  const ref = useContext(SidebarRefContext)
  const [width, setWidth] = useState(() => ref.current?.offsetWidth ?? 0)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    setWidth(el.offsetWidth)
    const observer = new ResizeObserver(entries => {
      const w = entries[0]?.contentRect.width ?? 0
      setWidth(w)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])

  return width
}
