import { useContext } from 'react'
import { SpeedLimitContext } from '@/context/SpeedLimitContext'

export function useSpeedLimits() {
    const context = useContext(SpeedLimitContext)
    if (!context) {
        throw new Error('useSpeedLimits must be used within SpeedLimitProvider')
    }
    return context
}
