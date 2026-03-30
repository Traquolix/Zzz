import { apiRequest } from './client'

export interface CoverageRange {
  start: number
  end: number
}

interface ApiFiberLine {
  id: string
  parentFiberId: string
  direction: number
  dataCoverage: CoverageRange[]
}

interface FibersResponse {
  results: ApiFiberLine[]
}

/**
 * Fetch fiber lines from the API and extract data coverage per cable.
 * Returns a Map keyed by parentFiberId (e.g. "carros") → coverage ranges.
 * Direction 0 is used as representative (coverage is per-cable, not per-direction).
 */
export async function fetchFiberCoverage(): Promise<Map<string, CoverageRange[]>> {
  const data = await apiRequest<FibersResponse>('/api/fibers')
  const coverage = new Map<string, CoverageRange[]>()
  for (const fiber of data.results) {
    // Only take direction 0 — coverage is the same for both directions
    if (fiber.direction === 0 && fiber.dataCoverage.length > 0) {
      coverage.set(fiber.parentFiberId, fiber.dataCoverage)
    }
  }
  return coverage
}
