import { useQuery } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import type { HistoryQuery } from '@/lib/api/endpoints/attendance'
import { teamKeys } from '@/features/team/queryKeys'

/** One employee's attendance for today, by id — the same cross-tenant/unknown
 * 404 ("User not found") either way, so this never leaks which case it was. */
export function useEmployeeAttendance(userId: string) {
  return useQuery({
    queryKey: teamKeys.member(userId),
    queryFn: ({ signal }) => attendanceApi.getUserAttendance(userId, undefined, signal),
    enabled: Boolean(userId),
  })
}

/** One employee's attendance history, paginated — same shape and defaults as
 * the self-service `useAttendanceHistory` (§11), just addressed by id. */
export function useEmployeeHistory(userId: string, params: HistoryQuery = {}) {
  return useQuery({
    queryKey: teamKeys.memberHistory(userId, params),
    queryFn: ({ signal }) => attendanceApi.getUserHistory(userId, params, signal),
    enabled: Boolean(userId),
    placeholderData: (previous) => previous,
  })
}
