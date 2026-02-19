import { createContext } from 'react'
import type { UserPreferences } from '@/types/user'

export type UserPreferencesContextType = {
    preferences: UserPreferences | null
    isLoading: boolean
    isSaving: boolean
    savePreferences: (prefs: UserPreferences) => Promise<void>
    updatePreferences: (partial: Partial<UserPreferences>) => Promise<void>
}

export const UserPreferencesContext = createContext<UserPreferencesContextType | null>(null)
