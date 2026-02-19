import { useEffect, useRef, useState, type ReactNode, useCallback } from 'react'
import { getAuthToken } from '@/api/client'
import { RealtimeContext, type RealtimeContextType } from './RealtimeContext'

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
                        console.error('RealtimeProvider: authentication timeout')
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

            ws.onmessage = (event) => {
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
                            reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS

                            // Now send queued subscriptions
                            for (const channel of pendingSubscriptionsRef.current) {
                                ws.send(JSON.stringify({ action: 'subscribe', channel }))
                            }
                            pendingSubscriptionsRef.current = []

                            startPingPong(ws)
                        } else {
                            console.error('RealtimeProvider: authentication failed:', parsed.message)
                            ws.close()
                        }
                        return
                    }

                    // Handle error responses
                    if (parsed.action === 'error') {
                        console.error('RealtimeProvider: server error:', parsed.message)
                        return
                    }

                    const { channel, data } = parsed
                    if (typeof channel !== 'string') return

                    subscriptionsRef.current.get(channel)?.forEach(cb => cb(data))
                } catch (error) {
                    console.error('RealtimeProvider: failed to parse WebSocket message', error)
                }
            }
        }

        const scheduleReconnect = () => {
            if (cancelledRef.current) return
            setReconnecting(true)

            const delay = reconnectDelayRef.current
            reconnectTimerRef.current = setTimeout(() => {
                if (!cancelledRef.current) {
                    reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS)
                    connect()
                }
            }, delay)
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
        subscribe,
    }

    return (
        <RealtimeContext.Provider value={value}>
            {children}
        </RealtimeContext.Provider>
    )
}
