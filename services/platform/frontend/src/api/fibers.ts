import { apiPaginatedRequest, type PaginatedResponse } from './client'
import type { FiberLine } from '@/types/fiber'

/**
 * Fetch all fibers (paginated envelope).
 */
export async function fetchFibers(): Promise<PaginatedResponse<FiberLine>> {
    return apiPaginatedRequest<FiberLine>('/api/fibers')
}
