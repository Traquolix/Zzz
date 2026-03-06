import '@testing-library/jest-dom/vitest'

// Polyfill localStorage for Node 22+ where globalThis.localStorage exists
// but is not a proper Storage instance (missing setItem/getItem/clear/etc.).
// This ensures jsdom-based tests can use localStorage normally.
if (typeof globalThis.localStorage === 'undefined' || typeof globalThis.localStorage.getItem !== 'function') {
  const storage = new Map<string, string>()
  const localStorageMock = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, String(value))
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
    get length() {
      return storage.size
    },
    key: (index: number) => [...storage.keys()][index] ?? null,
  }
  Object.defineProperty(globalThis, 'localStorage', {
    value: localStorageMock,
    writable: true,
    configurable: true,
  })
}
