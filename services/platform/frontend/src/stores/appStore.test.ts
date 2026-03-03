/**
 * TDD tests for the Zustand app store.
 *
 * Goal: Provide a global store for cross-cutting state that multiple
 * components need. Initial slices:
 *
 * 1. Connection slice — connected, authFailed status (pushed by RealtimeProvider)
 *
 * Components subscribe via selectors: `useAppStore(s => s.connected)` —
 * only re-renders when that specific slice changes.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from './appStore'

describe('appStore', () => {
    beforeEach(() => {
        // Reset store between tests
        useAppStore.setState(useAppStore.getInitialState())
    })

    describe('connection slice', () => {
        it('starts disconnected with no auth failure', () => {
            const state = useAppStore.getState()
            expect(state.connected).toBe(false)
            expect(state.authFailed).toBe(false)
        })

        it('setConnected updates connected state', () => {
            useAppStore.getState().setConnected(true)
            expect(useAppStore.getState().connected).toBe(true)

            useAppStore.getState().setConnected(false)
            expect(useAppStore.getState().connected).toBe(false)
        })

        it('setAuthFailed updates auth failure state', () => {
            useAppStore.getState().setAuthFailed(true)
            expect(useAppStore.getState().authFailed).toBe(true)
        })

        it('setConnected(true) clears authFailed', () => {
            useAppStore.getState().setAuthFailed(true)
            expect(useAppStore.getState().authFailed).toBe(true)

            useAppStore.getState().setConnected(true)
            expect(useAppStore.getState().authFailed).toBe(false)
        })
    })

})
