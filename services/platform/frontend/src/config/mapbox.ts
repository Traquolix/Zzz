import { logger } from '@/lib/logger'

// Mapbox token must be provided via environment variable VITE_MAPBOX_TOKEN
// Never commit tokens to source control
const token = import.meta.env.VITE_MAPBOX_TOKEN

if (!token) {
    logger.error('VITE_MAPBOX_TOKEN environment variable is not set. Map functionality will not work.')
}

export const MAPBOX_TOKEN = token || ''
