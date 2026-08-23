import { useQuery } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import { teamKeys } from '@/features/team/queryKeys'

/** Today's attendance across the caller's tenant (MANAGER/TENANT_ADMIN only —
 * enforced server-side; this hook is only ever mounted behind that route
 * guard). Summary counts come from the backend response verbatim — never
 * recomputed client-side (see `TeamAttendanceResponse.summary`). */
export function useTeamToday() {
  return useQuery({
    queryKey: teamKeys.today(),
    queryFn: ({ signal }) => attendanceApi.getTeamToday(undefined, signal),
  })
}
