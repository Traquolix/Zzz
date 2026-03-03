import { MapSelectionContext } from '@/context/MapSelectionContext'
import { createContextHook } from './createContextHook'

export const useMapSelection = createContextHook(MapSelectionContext, 'useMapSelection', 'MapSelectionProvider')
