/**
 * The one hook the rest of the app should use to know "who is signed in".
 * Components ask `isAuthenticated` / `user` / `hasRole(...)` — never decode a
 * JWT, never read `authStore` or `tokenStorage` directly. That indirection is
 * what let Phase 9/10 features stay ignorant of the token format entirely.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import * as authService from '@/lib/auth/session'
import type { UserRole } from '@/lib/api/types'
import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  const status = useAuthStore((state) => state.status)
  const user = useAuthStore((state) => state.user)
  const queryClient = useQueryClient()

  const loginMutation = useMutation({
    mutationFn: authService.login,
  })

  const logoutMutation = useMutation({
    mutationFn: authService.logout,
    onSettled: () => {
      // The user's own cached queries (attendance, profile, team roster) must
      // not survive into whoever uses this device next.
      queryClient.clear()
    },
  })

  const hasRole = useCallback(
    (...roles: UserRole[]) => (user ? (roles as string[]).includes(user.role) : false),
    [user],
  )

  return {
    status,
    isLoading: status === 'loading',
    isAuthenticated: status === 'authenticated',
    user,
    hasRole,
    login: loginMutation.mutateAsync,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    logout: logoutMutation.mutateAsync,
    isLoggingOut: logoutMutation.isPending,
  }
}
