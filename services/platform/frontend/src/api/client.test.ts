/**
 * TDD tests for token refresh mutex behavior.
 *
 * Goal: When multiple concurrent 401 responses trigger refresh attempts,
 * only ONE actual refresh request should be made. All callers should
 * receive the same result. The mutex must not leak — after resolution,
 * a new refresh can be triggered again.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// --- Mocks ---

// We need to control fetch at the global level
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

vi.mock('@/i18n', () => ({ default: { language: 'en' } }))

// Import after mocks
import { attemptTokenRefresh, setAuthToken, getAuthToken, clearAuthToken, apiRequest, ApiError } from './client'

describe('attemptTokenRefresh — mutex behavior', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        clearAuthToken()
    })

    afterEach(() => {
        clearAuthToken()
    })

    it('makes exactly one fetch when called once', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: 'new-token-1' }),
        })

        const result = await attemptTokenRefresh()

        expect(result).toBe(true)
        expect(getAuthToken()).toBe('new-token-1')
        // Only one fetch call for the refresh endpoint
        const refreshCalls = mockFetch.mock.calls.filter(
            call => typeof call[0] === 'string' && call[0].includes('/auth/refresh')
        )
        expect(refreshCalls).toHaveLength(1)
    })

    it('makes exactly one fetch when called concurrently 5 times', async () => {
        let resolveRefresh: (value: Response) => void
        const refreshPromise = new Promise<Response>(r => { resolveRefresh = r })
        mockFetch.mockReturnValueOnce(refreshPromise)

        // Fire 5 concurrent refresh attempts
        const results = Promise.all([
            attemptTokenRefresh(),
            attemptTokenRefresh(),
            attemptTokenRefresh(),
            attemptTokenRefresh(),
            attemptTokenRefresh(),
        ])

        // Resolve the single fetch
        resolveRefresh!({
            ok: true,
            json: async () => ({ token: 'shared-token' }),
        } as Response)

        const outcomes = await results

        // All 5 callers get the same success result
        expect(outcomes).toEqual([true, true, true, true, true])
        expect(getAuthToken()).toBe('shared-token')

        // Only ONE actual network request was made
        const refreshCalls = mockFetch.mock.calls.filter(
            call => typeof call[0] === 'string' && call[0].includes('/auth/refresh')
        )
        expect(refreshCalls).toHaveLength(1)
    })

    it('all concurrent callers receive false when refresh fails', async () => {
        mockFetch.mockResolvedValueOnce({ ok: false, json: async () => ({}) })

        const results = await Promise.all([
            attemptTokenRefresh(),
            attemptTokenRefresh(),
            attemptTokenRefresh(),
        ])

        expect(results).toEqual([false, false, false])
    })

    it('allows a new refresh after the previous one completes', async () => {
        // First refresh succeeds
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: 'token-round-1' }),
        })
        await attemptTokenRefresh()
        expect(getAuthToken()).toBe('token-round-1')

        // Second refresh (new round) — should create a NEW fetch
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: 'token-round-2' }),
        })
        await attemptTokenRefresh()
        expect(getAuthToken()).toBe('token-round-2')

        // Two separate refresh calls total
        const refreshCalls = mockFetch.mock.calls.filter(
            call => typeof call[0] === 'string' && call[0].includes('/auth/refresh')
        )
        expect(refreshCalls).toHaveLength(2)
    })

    it('mutex resets even when refresh throws', async () => {
        mockFetch.mockRejectedValueOnce(new Error('network error'))
        const result1 = await attemptTokenRefresh()
        expect(result1).toBe(false)

        // Mutex should be cleared — next call creates a new request
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: async () => ({ token: 'recovered' }),
        })
        const result2 = await attemptTokenRefresh()
        expect(result2).toBe(true)
        expect(getAuthToken()).toBe('recovered')
    })
})

describe('apiRequest — empty response handling', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        clearAuthToken()
    })

    afterEach(() => {
        clearAuthToken()
    })

    it('DELETE request with empty body resolves without error', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => '', // Empty body
        })

        const result = await apiRequest('/api/resource/123', {
            method: 'DELETE',
            requiresAuth: false,
        })

        // For DELETE, empty body should return undefined
        expect(result).toBeUndefined()
    })

    it('PUT request with empty body resolves without error', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => '', // Empty body
        })

        const result = await apiRequest('/api/resource/123', {
            method: 'PUT',
            body: { some: 'data' },
            requiresAuth: false,
        })

        // For PUT, empty body should return undefined (write operations don't expect a body back)
        expect(result).toBeUndefined()
    })

    it('GET request with empty body throws ApiError', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => '', // Empty body
        })

        try {
            await apiRequest('/api/data', {
                method: 'GET',
                requiresAuth: false,
            })
            expect.fail('Should have thrown ApiError')
        } catch (error) {
            expect(error).toBeInstanceOf(ApiError)
            expect((error as ApiError).message).toBe('Empty response body')
            expect((error as ApiError).status).toBe(0)
        }
    })

    it('POST request with empty body throws ApiError', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => '', // Empty body
        })

        try {
            await apiRequest('/api/data', {
                method: 'POST',
                body: { test: 'data' },
                requiresAuth: false,
            })
            expect.fail('Should have thrown ApiError')
        } catch (error) {
            expect(error).toBeInstanceOf(ApiError)
            expect((error as ApiError).message).toBe('Empty response body')
        }
    })

    it('GET request with valid JSON body resolves correctly', async () => {
        const expectedData = { id: 123, name: 'test' }
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => JSON.stringify(expectedData),
        })

        const result = await apiRequest('/api/data', {
            method: 'GET',
            requiresAuth: false,
        })

        expect(result).toEqual(expectedData)
    })

    it('DELETE request with valid JSON body resolves correctly', async () => {
        const expectedData = { success: true }
        mockFetch.mockResolvedValueOnce({
            ok: true,
            status: 200,
            text: async () => JSON.stringify(expectedData),
        })

        const result = await apiRequest('/api/resource/123', {
            method: 'DELETE',
            requiresAuth: false,
        })

        expect(result).toEqual(expectedData)
    })

    it('retry path applies same empty body logic for DELETE', async () => {
        mockFetch
            .mockResolvedValueOnce({
                ok: false,
                status: 401, // Trigger refresh
                json: async () => ({ detail: 'Unauthorized' }),
            })
            .mockResolvedValueOnce({
                ok: true, // Refresh succeeds
                json: async () => ({ token: 'new-token' }),
            })
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                text: async () => '', // Empty body on retry
            })

        setAuthToken('old-token')

        const result = await apiRequest('/api/resource/123', {
            method: 'DELETE',
            requiresAuth: true,
        })

        expect(result).toBeUndefined()
    })

    it('retry path applies same empty body logic for GET — throws ApiError', async () => {
        mockFetch
            .mockResolvedValueOnce({
                ok: false,
                status: 401, // Trigger refresh
                json: async () => ({ detail: 'Unauthorized' }),
            })
            .mockResolvedValueOnce({
                ok: true, // Refresh succeeds
                json: async () => ({ token: 'new-token' }),
            })
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                text: async () => '', // Empty body on retry
            })

        setAuthToken('old-token')

        try {
            await apiRequest('/api/data', {
                method: 'GET',
                requiresAuth: true,
            })
            expect.fail('Should have thrown ApiError')
        } catch (error) {
            expect(error).toBeInstanceOf(ApiError)
            expect((error as ApiError).message).toBe('Empty response body')
        }
    })
})
