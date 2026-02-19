import { apiRequest } from './client'
import type { UserPreferences } from '@/types/user'

/**
 * Load user preferences from server
 */
export async function loadPreferences(): Promise<UserPreferences> {
    try {
        return await apiRequest<UserPreferences>('/api/user/preferences')
    } catch {
        return {}
    }
}

/**
 * Save user preferences to server
 */
export async function savePreferences(preferences: UserPreferences): Promise<void> {
    await apiRequest('/api/user/preferences', {
        method: 'PUT',
        body: preferences
    })
}
