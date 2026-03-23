import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useRealtime } from '@/hooks/useRealtime'

export function ConnectionBanner() {
  const { connected, reconnecting, authFailed } = useRealtime()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const hasEverConnectedRef = useRef(false)
  const wasDisconnectedRef = useRef(false)

  // Track whether we've ever had a successful connection
  useEffect(() => {
    if (connected) hasEverConnectedRef.current = true
  }, [connected])

  // Auto-invalidate active queries when connection is restored after a real drop
  useEffect(() => {
    if (!connected) {
      if (hasEverConnectedRef.current) wasDisconnectedRef.current = true
      return
    }
    if (wasDisconnectedRef.current) {
      wasDisconnectedRef.current = false
      queryClient.invalidateQueries({ refetchType: 'active' })
    }
  }, [connected, queryClient])

  // Don't show anything until we've connected at least once
  if (!hasEverConnectedRef.current) return null
  if (connected && !reconnecting && !authFailed) return null

  let message: string
  let color: string
  let showLogin = false

  if (authFailed) {
    message = t('connection.authFailed')
    color = 'var(--proto-red)'
    showLogin = true
  } else if (reconnecting) {
    message = t('connection.reconnecting')
    color = 'var(--proto-amber)'
  } else {
    message = t('connection.disconnected')
    color = 'var(--proto-red)'
  }

  return (
    <div
      className="absolute top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 py-3 text-cq-xs font-medium pointer-events-none"
      style={{
        background: `linear-gradient(135deg, color-mix(in srgb, ${color} 15%, transparent), color-mix(in srgb, ${color} 8%, transparent))`,
        borderBottom: `1px solid color-mix(in srgb, ${color} 25%, transparent)`,
        color,
      }}
    >
      {reconnecting && !authFailed && (
        <span
          className="inline-block w-3 h-3 border-[1.5px] rounded-full animate-spin"
          style={{
            borderColor: `color-mix(in srgb, ${color} 30%, transparent)`,
            borderTopColor: color,
          }}
        />
      )}
      <span>{message}</span>
      {showLogin && (
        <a
          href="/login"
          className="underline underline-offset-2 hover:brightness-125 transition-all pointer-events-auto"
          style={{ color }}
        >
          {t('connection.reLogin')}
        </a>
      )}
    </div>
  )
}
