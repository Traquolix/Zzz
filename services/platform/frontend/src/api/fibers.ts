import { apiRequest } from './client'

export interface CoverageRange {
  start: number
  end: number
}

export interface ApiFiber {
  id: string // "carros:0"
  parentFiberId: string // "carros"
  direction: number
  name: string
  color: string
  coordinates: ([number, number] | [null, null])[]
  coordsPrecomputed: boolean
  landmarks: { channel: number; name: string }[] | null
  dataCoverage: CoverageRange[]
}

interface FibersResponse {
  results: ApiFiber[]
}

/**
 * Fetch all directional fibers from the API.
 * Returns the raw API fiber objects for transformation by the FiberContext.
 */
export async function fetchFibers(): Promise<ApiFiber[]> {
  const data = await apiRequest<FibersResponse>('/api/fibers')
  return data.results
}
