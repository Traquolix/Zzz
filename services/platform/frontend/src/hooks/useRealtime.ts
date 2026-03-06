import { RealtimeContext } from '@/context/RealtimeContext'
import { createContextHook } from './createContextHook'

export const useRealtime = createContextHook(RealtimeContext, 'useRealtime', 'RealtimeProvider')
