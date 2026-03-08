import { useEffect, useRef, useState, type ReactNode, useCallback } from 'react'
import { getAuthToken } from '@/api/client'
import { logger } from '@/lib/logger'
import { RealtimeContext, type RealtimeContextType, type DataFlow } from './RealtimeContext'
import { useAppStore } from '@/stores/appStore'

const PING_INTERVAL_MS = 30_000
const INITIAL_RECONNECT_DELAY_MS = 1_000
const MAX_RECONNECT_DELAY_MS = 30_000
const TOKEN_POLL_INTERVAL_MS = 500
const TOKEN_POLL_MAX_ATTEMPTS = 20
const AUTH_TIMEOUT_MS = 30_000

export function RealtimeProvider({ children, url }: { children: ReactNode; url: string }) {
  const socketRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [authFailed, setAuthFailed] = useState(false)
  const [flow, setFlowState] = useState<DataFlow>('sim')
  const flowRef = useRef<DataFlow>('sim')
  const [availableFlows, setAvailableFlows] = useState<DataFlow[]>(['sim'])
  const flowChangeCallbacksRef = useRef<Set<(flow: DataFlow) => void>>(new Set())
  const subscriptionsRef = useRef<Map<string, Set<(data: unknown) => void>>>(new Map())
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const authTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cancelledRef = useRef(false)
  const authenticatedRef = useRef(false)
  const pendingSubscriptionsRef = useRef<string[]>([])

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current)
      pingTimerRef.current = null
    }
    if (authTimeoutRef.current) {
      clearTimeout(authTimeoutRef.current)
      authTimeoutRef.current = null
    }
  }, [])

  const startPingPong = useCallback((ws: WebSocket) => {
    if (pingTimerRef.current) clearInterval(pingTimerRef.current)
    pingTimerRef.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'ping' }))
      }
    }, PING_INTERVAL_MS)
  }, [])

  const setFlow = useCallback((newFlow: DataFlow) => {
    const ws = socketRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN || !authenticatedRef.current) return
    ws.send(JSON.stringify({ action: 'set_flow', flow: newFlow }))
    flowRef.current = newFlow
    setFlowState(newFlow)
    // Notify all registered callbacks so hooks can clear state
    flowChangeCallbacksRef.current.forEach(cb => cb(newFlow))
  }, [])

  const onFlowChange = useCallback((cb: (flow: DataFlow) => void) => {
    flowChangeCallbacksRef.current.add(cb)
    return () => {
      flowChangeCallbacksRef.current.delete(cb)
    }
  }, [])

  useEffect(() => {
    cancelledRef.current = false

    let tokenPollTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      const token = getAuthToken()
      if (!token) {
        // Token not yet available — poll until auth completes
        let attempts = 0
        const poll = () => {
          if (cancelledRef.current) return
          attempts++
          const t = getAuthToken()
          if (t) {
            tokenPollTimer = null
            connect()
          } else if (attempts < TOKEN_POLL_MAX_ATTEMPTS) {
            tokenPollTimer = setTimeout(poll, TOKEN_POLL_INTERVAL_MS)
          } else {
            // Token polling exhausted — surface auth failure
            setAuthFailed(true)
          }
        }
        tokenPollTimer = setTimeout(poll, TOKEN_POLL_INTERVAL_MS)
        return
      }

      // Connect without token in URL (security: tokens in URLs appear in logs/history)
      // Token is sent via initial 'authenticate' message after connection
      const ws = new WebSocket(url)

      ws.onopen = () => {
        if (cancelledRef.current) {
          ws.close()
          return
        }

        socketRef.current = ws
        authenticatedRef.current = false

        // Queue existing subscriptions to be sent after authentication
        pendingSubscriptionsRef.current = Array.from(subscriptionsRef.current.keys())

        // Send authentication message first
        ws.send(JSON.stringify({ action: 'authenticate', token }))

        // Set auth timeout - close connection if no auth response
        authTimeoutRef.current = setTimeout(() => {
          if (!authenticatedRef.current && ws.readyState === WebSocket.OPEN) {
            logger.error('RealtimeProvider: authentication timeout')
            ws.close()
          }
        }, AUTH_TIMEOUT_MS)
      }

      ws.onclose = () => {
        if (cancelledRef.current) return
        socketRef.current = null
        authenticatedRef.current = false
        pendingSubscriptionsRef.current = []
        setConnected(false)
        clearTimers()
        scheduleReconnect()
      }

      ws.onerror = () => {
        // onclose will fire after onerror, which handles reconnection
      }

      ws.onmessage = event => {
        try {
          const parsed = JSON.parse(event.data)

          // Handle pong responses (just ignore them — they keep the connection alive)
          if (parsed.action === 'pong') return

          // Handle authentication response
          if (parsed.action === 'authenticated') {
            if (authTimeoutRef.current) {
              clearTimeout(authTimeoutRef.current)
              authTimeoutRef.current = null
            }

            if (parsed.success) {
              authenticatedRef.current = true
              setConnected(true)
              setReconnecting(false)
              setAuthFailed(false)
              reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS

              // Read available flows from auth response
              const flows: DataFlow[] = parsed.available_flows ?? ['sim']
              setAvailableFlows(flows)

              // Preserve user's flow choice across reconnects; fall back if unavailable
              const preferred = flowRef.current
              const resolvedFlow: DataFlow = flows.includes(preferred)
                ? preferred
                : flows.includes('live')
                  ? 'live'
                  : 'sim'
              flowRef.current = resolvedFlow
              setFlowState(resolvedFlow)

              // Send initial set_flow to backend
              ws.send(JSON.stringify({ action: 'set_flow', flow: resolvedFlow }))

              // Now send queued subscriptions
              for (const channel of pendingSubscriptionsRef.current) {
                ws.send(JSON.stringify({ action: 'subscribe', channel }))
              }
              pendingSubscriptionsRef.current = []

              startPingPong(ws)
            } else {
              logger.error('RealtimeProvider: authentication failed:', parsed.message)
              setAuthFailed(true)
              ws.close()
            }
            return
          }

          // Handle flow_changed confirmation (no-op, already handled optimistically)
          if (parsed.action === 'flow_changed') return

          // Handle error responses
          if (parsed.action === 'error') {
            logger.error('RealtimeProvider: server error:', parsed.message)
            return
          }

          const { channel, data } = parsed
          if (typeof channel !== 'string') return

          subscriptionsRef.current.get(channel)?.forEach(cb => cb(data))
        } catch (error) {
          logger.error('RealtimeProvider: failed to parse WebSocket message', error)
        }
      }
    }

    const scheduleReconnect = () => {
      if (cancelledRef.current) return
      setReconnecting(true)

      const delay = reconnectDelayRef.current
      // Add ±50% jitter to prevent thundering herd on mass reconnect
      const jitter = delay * (0.5 + Math.random())
      reconnectTimerRef.current = setTimeout(() => {
        if (!cancelledRef.current) {
          reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS)
          connect()
        }
      }, jitter)
    }

    connect()

    return () => {
      cancelledRef.current = true
      if (tokenPollTimer) clearTimeout(tokenPollTimer)
      clearTimers()
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [url, clearTimers, startPingPong])

  // Sync connection state to Zustand store for cross-cutting consumers
  useEffect(() => {
    useAppStore.getState().setConnected(connected)
  }, [connected])

  useEffect(() => {
    useAppStore.getState().setAuthFailed(authFailed)
  }, [authFailed])

  // Sync flow state to Zustand store
  useEffect(() => {
    useAppStore.getState().setFlow(flow)
  }, [flow])

  const subscribe = useCallback((channel: string, callback: (data: unknown) => void) => {
    if (!subscriptionsRef.current.has(channel)) {
      subscriptionsRef.current.set(channel, new Set())
    }
    subscriptionsRef.current.get(channel)!.add(callback)

    // Only send subscription if authenticated; otherwise it will be sent after auth
    if (authenticatedRef.current && socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ action: 'subscribe', channel }))
    } else if (socketRef.current?.readyState === WebSocket.OPEN && !pendingSubscriptionsRef.current.includes(channel)) {
      // Socket open but not authenticated yet - queue the subscription
      pendingSubscriptionsRef.current.push(channel)
    }

    return () => {
      subscriptionsRef.current.get(channel)?.delete(callback)
      if (subscriptionsRef.current.get(channel)?.size === 0) {
        subscriptionsRef.current.delete(channel)
        if (authenticatedRef.current && socketRef.current?.readyState === WebSocket.OPEN) {
          socketRef.current.send(JSON.stringify({ action: 'unsubscribe', channel }))
        }
      }
    }
  }, [])

  const value: RealtimeContextType = {
    connected,
    reconnecting,
    authFailed,
    flow,
    availableFlows,
    setFlow,
    onFlowChange,
    subscribe,
  }

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>
}
