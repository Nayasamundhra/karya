import { useQuery } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import { teamKeys } from '@/features/team/queryKeys'

/** Hours worked today/this week/this month across the caller's tenant
 * (MANAGER/TENANT_ADMIN only — enforced server-side). Unlike the rest of
 * this feature's queries, the backend computes an open session's
 * contribution up to the moment of the request — the number is meant to
 * visibly move while someone is checked in, so this polls on a short
 * interval instead of relying on the default 30s staleTime + refetch-on-
 * focus alone. */
export function useTeamHours() {
  return useQuery({
    queryKey: teamKeys.hours(),
    queryFn: ({ signal }) => attendanceApi.getTeamHours(signal),
    refetchInterval: 60_000,
  })
}
