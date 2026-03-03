import { AuthContext } from '@/context/AuthContext'
import { createContextHook } from './createContextHook'

export const useAuth = createContextHook(AuthContext, 'useAuth', 'AuthProvider')
