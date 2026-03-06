import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import prettierConfig from 'eslint-config-prettier'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettierConfig,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      // These rules are overly strict for common React patterns
      'react-hooks/set-state-in-effect': 'off', // Initializing state from async data is a valid pattern
      'react-hooks/purity': 'off', // Date.now() in useRef/useState initializers is acceptable
      'react-hooks/refs': 'off', // Syncing refs in render before effects is a common pattern
      'react-hooks/preserve-manual-memoization': 'off', // React Compiler optimization hints, not errors
      'react-refresh/only-export-components': 'off', // Common pattern to export helpers alongside components
    },
  },
])
