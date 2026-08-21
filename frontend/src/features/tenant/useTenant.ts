import { useQuery } from '@tanstack/react-query'

import * as tenantApi from '@/lib/api/endpoints/tenant'
import { useAuth } from '@/features/auth/useAuth'

/**
 * The caller's own organisation — display/context only (§25: tenant_id is
 * never something the frontend sends to decide access; every request is
 * scoped by the backend from the bearer token regardless of what this hook
 * returns). Used for showing the org name in the shell header and on the
 * profile page.
 */
export function useTenant() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: ['tenant', 'me'],
    queryFn: ({ signal }) => tenantApi.getOwnTenant(signal),
    enabled: isAuthenticated,
    // The organisation's name changes rarely; there is no reason to refetch
    // it as aggressively as attendance data (contrast with §22's warning
    // about attendance staleness — this is the opposite kind of resource).
    staleTime: 5 * 60 * 1000,
  })
}
