/**
 * Check-in / check-out mutations. Both send only the four evidence fields
 * the backend's `AttendanceActionRequest` accepts (§6) — there is no field
 * here a caller could set to influence tenant, user, timestamp or verdict,
 * because the request type itself (generated from the OpenAPI schema)
 * doesn't have one.
 *
 * A refused attempt (`success: false`) is still a normal resolved mutation,
 * matching the backend's "business refusal is HTTP 200" design (CLAUDE.md) —
 * `onSuccess` fires either way and refreshes `/me` + history (§17), since a
 * refusal can still have changed nothing or, on a state-conflict refusal,
 * reveal the caller's real current state. Only a thrown `ApiError` (network,
 * 401, 429, 5xx) reaches the caller as a rejected mutation.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'

import * as attendanceApi from '@/lib/api/endpoints/attendance'
import type { AttendanceActionRequest } from '@/lib/api/types'
import { attendanceKeys } from '@/features/attendance/queryKeys'

function useInvalidateAttendance() {
  const queryClient = useQueryClient()
  return () => {
    queryClient.invalidateQueries({ queryKey: attendanceKeys.all })
  }
}

export function useCheckIn() {
  const invalidate = useInvalidateAttendance()
  return useMutation({
    mutationFn: (payload: AttendanceActionRequest) => attendanceApi.checkIn(payload),
    onSuccess: invalidate,
  })
}

export function useCheckOut() {
  const invalidate = useInvalidateAttendance()
  return useMutation({
    mutationFn: (payload: AttendanceActionRequest) => attendanceApi.checkOut(payload),
    onSuccess: invalidate,
  })
}
