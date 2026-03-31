import { createContext, useContext, useReducer, useCallback, type ReactNode } from 'react'
import { toast } from 'sonner'
import type { MapPageState, MapPageAction } from '../types'
import { reducer, initialState } from '../reducer'

interface DashboardContextValue {
  state: MapPageState
  dispatch: React.Dispatch<MapPageAction>
}

const DashboardContext = createContext<DashboardContextValue | null>(null)

export function DashboardProvider({
  children,
  removeSection,
}: {
  children: ReactNode
  removeSection: (id: string) => Promise<void>
}) {
  const [state, rawDispatch] = useReducer(reducer, initialState)

  const dispatch = useCallback(
    (action: MapPageAction) => {
      if (action.type === 'DELETE_SECTION') {
        removeSection(action.id).catch(() => {
          toast.error('Failed to delete section')
        })
      }
      rawDispatch(action)
    },
    [removeSection],
  )

  return <DashboardContext.Provider value={{ state, dispatch }}>{children}</DashboardContext.Provider>
}

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext)
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider')
  return ctx
}
