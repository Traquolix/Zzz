import { apiRequest } from './client'
import type { FiberLine } from '@/types/fiber'

/**
 * Fetch all fibers
 */
export async function fetchFibers(): Promise<FiberLine[]> {
    return apiRequest<FiberLine[]>('/api/fibers')
}
