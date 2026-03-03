/**
 * TDD tests for RealtimeProvider — WebSocket auth failure handling.
 *
 * Goal: When the WebSocket can't authenticate (token polling exhausts,
 * or server rejects auth), the provider must surface an `authFailed`
 * flag so the UI can redirect to login or show an error banner.
 * It must NOT silently die.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

// --- Mocks ---

let mockToken: string | null = 'valid-token'
vi.mock('@/api/client', () => ({
    getAuthToken: () => mockToken,
}))

// Minimal WebSocket mock
class MockWebSocket {
    static OPEN = 1
    static CONNECTING = 0
    static CLOSING = 2
    static CLOSED = 3

    readyState = MockWebSocket.CONNECTING
    onopen: (() => void) | null = null
    onclose: (() => void) | null = null
    onmessage: ((event: { data: string }) => void) | null = null
    onerror: (() => void) | null = null

    url: string
    constructor(url: string) {
        this.url = url
        // Auto-fire onopen in next tick
        setTimeout(() => {
            this.readyState = MockWebSocket.OPEN
            this.onopen?.()
        }, 0)
    }

    send = vi.fn()
    close = vi.fn(() => {
        this.readyState = MockWebSocket.CLOSED
        setTimeout(() => this.onclose?.(), 0)
    })

    // Test helper: simulate server message
    _receive(data: unknown) {
        this.onmessage?.({ data: JSON.stringify(data) })
    }
}

let wsInstances: MockWebSocket[] = []
const mockWebSocketClass = class extends MockWebSocket {
    constructor(url: string) {
        super(url)
        wsInstances.push(this)
    }
}
vi.stubGlobal('WebSocket', mockWebSocketClass as any)

import { RealtimeProvider } from './RealtimeProvider'
import { RealtimeContext } from './RealtimeContext'
import { useContext } from 'react'

function useTestRealtime() {
    return useContext(RealtimeContext)
}

function wrapper({ children }: { children: ReactNode }) {
    return <RealtimeProvider url="ws://test">{children}</RealtimeProvider>
}

describe('RealtimeProvider — auth failure handling', () => {
    beforeEach(() => {
        vi.useFakeTimers()
        vi.clearAllMocks()
        wsInstances = []
        mockToken = 'valid-token'
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('exposes authFailed=false when authentication succeeds', async () => {
        const { result } = renderHook(useTestRealtime, { wrapper })

        // Advance to let WebSocket connect
        await act(async () => { vi.advanceTimersByTime(10) })

        // Simulate successful auth response
        const ws = wsInstances[0]
        await act(async () => {
            ws._receive({ action: 'authenticated', success: true })
        })

        expect(result.current?.connected).toBe(true)
        expect(result.current?.authFailed).toBe(false)
    })

    it('sets authFailed=true when token polling exhausts without finding a token', async () => {
        mockToken = null // No token available

        const { result } = renderHook(useTestRealtime, { wrapper })

        // Advance through all 20 poll attempts (500ms each = 10s)
        await act(async () => {
            vi.advanceTimersByTime(20 * 500 + 100)
        })

        expect(result.current?.authFailed).toBe(true)
        expect(result.current?.connected).toBe(false)
    })

    it('sets authFailed=true when server rejects authentication', async () => {
        const { result } = renderHook(useTestRealtime, { wrapper })

        await act(async () => { vi.advanceTimersByTime(10) })

        const ws = wsInstances[0]
        await act(async () => {
            ws._receive({ action: 'authenticated', success: false, message: 'invalid token' })
        })

        // WebSocket closes after failed auth, which should surface authFailed
        await act(async () => { vi.advanceTimersByTime(10) })

        expect(result.current?.authFailed).toBe(true)
    })

    it('authFailed stays false during normal reconnect cycle', async () => {
        const { result } = renderHook(useTestRealtime, { wrapper })

        // Let WebSocket connect
        await act(async () => { vi.advanceTimersByTime(10) })

        const ws = wsInstances[0]
        // Authenticate successfully first
        await act(async () => {
            ws._receive({ action: 'authenticated', success: true })
        })
        expect(result.current?.connected).toBe(true)
        expect(result.current?.authFailed).toBe(false)

        // Simulate disconnect (network drop, not auth failure)
        await act(async () => {
            ws.readyState = MockWebSocket.CLOSED
            ws.onclose?.()
        })

        expect(result.current?.connected).toBe(false)
        // authFailed should remain false — this was a network issue, not auth
        expect(result.current?.authFailed).toBe(false)
    })
})
