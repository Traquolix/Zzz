/**
 * Tests for createContextHook factory.
 *
 * Verifies that generated hooks:
 * 1. Throw with descriptive message when used outside provider
 * 2. Return context value when inside provider
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { createContext, type ReactNode } from 'react'
import { createContextHook } from './createContextHook'

type TestContext = { value: number }

const TestCtx = createContext<TestContext | null>(null)
const useTest = createContextHook(TestCtx, 'useTest', 'TestProvider')

describe('createContextHook', () => {
  it('throws when used outside provider', () => {
    // renderHook catches the error boundary — we need to suppress console.error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderHook(() => useTest())).toThrow('useTest must be used within TestProvider')
    spy.mockRestore()
  })

  it('returns context value inside provider', () => {
    function wrapper({ children }: { children: ReactNode }) {
      return <TestCtx.Provider value={{ value: 42 }}>{children}</TestCtx.Provider>
    }
    const { result } = renderHook(() => useTest(), { wrapper })
    expect(result.current.value).toBe(42)
  })
})
