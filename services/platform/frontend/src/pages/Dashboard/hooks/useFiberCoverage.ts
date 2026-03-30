import { useQuery } from '@tanstack/react-query'
import { fetchFiberCoverage, type CoverageRange } from '@/api/fibers'

/**
 * Fetch pipeline data coverage ranges per cable from the API.
 * Returns a stable Map<parentCableId, CoverageRange[]>.
 * Coverage rarely changes, so we use a long staleTime.
 */
export function useFiberCoverage() {
  const { data: coverageMap } = useQuery({
    queryKey: ['fiber-coverage'],
    queryFn: fetchFiberCoverage,
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  })

  return coverageMap ?? new Map<string, CoverageRange[]>()
}
