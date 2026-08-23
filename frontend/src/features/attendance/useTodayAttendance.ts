import { useQuery } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import { attendanceKeys } from '@/features/attendance/queryKeys'

/** The caller's own attendance for today (UTC) — §12. Server state only;
 * nothing here is duplicated into a store. */
export function useTodayAttendance() {
  return useQuery({
    queryKey: attendanceKeys.today(),
    queryFn: ({ signal }) => attendanceApi.getMyAttendance(undefined, signal),
  })
}
