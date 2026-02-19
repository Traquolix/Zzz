import { useContext } from 'react'
import { MapSelectionContext } from '@/context/MapSelectionContext'

export function useMapSelection() {
    const context = useContext(MapSelectionContext)
    if (!context) {
        throw new Error('useMapSelection must be used within a MapSelectionProvider')
    }
    return context
}
