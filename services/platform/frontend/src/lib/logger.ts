const isDev = import.meta.env.DEV

export const logger = {
  error: (...args: unknown[]) => {
    if (isDev) console.error('[SequoIA]', ...args)
  },
  warn: (...args: unknown[]) => {
    if (isDev) console.warn('[SequoIA]', ...args)
  },
  debug: (...args: unknown[]) => {
    if (isDev) console.log('[SequoIA]', ...args)
  },
}
