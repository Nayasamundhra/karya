import { useQuery } from '@tanstack/react-query'

import { useAuth } from '@/features/auth/useAuth'
import { isApiError } from '@/lib/api/errors'
import * as tenantApi from '@/lib/api/endpoints/tenant'

/**
 * The tenant's attendance location, or `null` if none has been set up yet.
 *
 * `null` is a real, expected value here — a fresh (or not-yet-onboarded-past-
 * step-one) tenant genuinely has no location, and that is not an error the
 * caller should render `ErrorState` for; it's the cue to show a "set one up"
 * form instead (see `AttendanceLocationCard`). Only a *non*-404 failure
 * (network, 500, ...) surfaces as a real query error.
 */
export function useLocation() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: ['tenant', 'location'],
    queryFn: async ({ signal }) => {
      try {
        return await tenantApi.getOwnLocation(signal)
      } catch (error) {
        if (isApiError(error) && error.kind === 'not_found') return null
        throw error
      }
    },
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  })
}
