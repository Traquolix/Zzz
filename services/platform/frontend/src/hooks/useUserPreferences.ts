import { UserPreferencesContext } from '@/context/UserPreferencesContext'
import { createContextHook } from './createContextHook'

export const useUserPreferences = createContextHook(UserPreferencesContext, 'useUserPreferences', 'UserPreferencesProvider')
