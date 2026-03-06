/**
 * Factory for creating type-safe context accessor hooks.
 *
 * Eliminates boilerplate: useContext() → null check → throw.
 * Every hook produced by this factory has identical error behavior:
 * throws with a descriptive message naming the hook and its required provider.
 */
import { useContext, type Context } from 'react'

export function createContextHook<T>(context: Context<T | null>, hookName: string, providerName: string): () => T {
  return () => {
    const value = useContext(context)
    if (!value) {
      throw new Error(`${hookName} must be used within ${providerName}`)
    }
    return value
  }
}
