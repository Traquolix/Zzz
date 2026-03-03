import { SpeedLimitContext } from '@/context/SpeedLimitContext'
import { createContextHook } from './createContextHook'

export const useSpeedLimits = createContextHook(SpeedLimitContext, 'useSpeedLimits', 'SpeedLimitProvider')
