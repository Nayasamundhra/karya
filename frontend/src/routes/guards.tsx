/**
 * Route guards. Read this alongside §7: everything here is UX only. It
 * spares an authenticated STAFF user from ever seeing a `/admin/users` shell
 * they have no use for, but the actual security boundary is the backend's
 * `require_roles` dependency (see backend `app/api/deps.py`) — a STAFF
 * token sent straight at that endpoint over HTTP still gets a 403 no matter
 * what this file does. Nothing here should ever be mistaken for that
 * boundary.
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import type { UserRole } from '@/lib/api/types'
import { FullScreenSpinner } from '@/components/layout/FullScreenSpinner'

export function RequireAuth() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return <FullScreenSpinner label="Checking your session…" />
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />
  return <Outlet />
}

/** Nest inside `RequireAuth` — assumes a user already exists. */
export function RequireRole({ roles }: { roles: readonly UserRole[] }) {
  const { hasRole } = useAuth()
  if (!hasRole(...roles)) return <Navigate to="/forbidden" replace />
  return <Outlet />
}

/** The inverse of `RequireAuth` — keeps a signed-in user off `/login`. */
export function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  if (isLoading) return <FullScreenSpinner label="Loading…" />
  if (isAuthenticated) return <Navigate to="/" replace />
  return <>{children}</>
}
