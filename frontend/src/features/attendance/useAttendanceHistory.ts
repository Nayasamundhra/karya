import { useQuery } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import type { HistoryQuery } from '@/lib/api/endpoints/attendance'
import { attendanceKeys } from '@/features/attendance/queryKeys'

/** One page of the caller's own attendance history (§11) — pagination and
 * date-range params are the existing backend contract verbatim, never
 * reshaped here. `placeholderData` keeps the previous page's rows on screen
 * while the next page loads, instead of flashing back to a loading state. */
export function useAttendanceHistory(params: HistoryQuery = {}) {
  return useQuery({
    queryKey: attendanceKeys.history(params),
    queryFn: ({ signal }) => attendanceApi.getMyHistory(params, signal),
    placeholderData: (previous) => previous,
  })
}
