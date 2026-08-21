/**
 * Attendance endpoints.
 *
 * Phase 8 wires these up for later use (they back the geolocation/QR
 * foundations) but the actual check-in/check-out screen is Phase 9's job —
 * see `src/features/attendance/README.md`.
 */
import { apiFetch } from '@/lib/api/client'
import type {
  AttendanceActionRequest,
  AttendanceActionResponse,
  AttendanceHistoryResponse,
  AttendanceTodayResponse,
  TeamAttendanceResponse,
} from '@/lib/api/types'

export function checkIn(payload: AttendanceActionRequest): Promise<AttendanceActionResponse> {
  return apiFetch<AttendanceActionResponse>('/api/v1/attendance/check-in', { method: 'POST', body: payload })
}

export function checkOut(payload: AttendanceActionRequest): Promise<AttendanceActionResponse> {
  return apiFetch<AttendanceActionResponse>('/api/v1/attendance/check-out', { method: 'POST', body: payload })
}

export function getMyAttendance(day?: string, signal?: AbortSignal): Promise<AttendanceTodayResponse> {
  return apiFetch<AttendanceTodayResponse>('/api/v1/attendance/me', { query: { day }, signal })
}

export interface HistoryQuery {
  fromDate?: string
  toDate?: string
  page?: number
  pageSize?: number
}

export function getMyHistory(params: HistoryQuery = {}, signal?: AbortSignal): Promise<AttendanceHistoryResponse> {
  return apiFetch<AttendanceHistoryResponse>('/api/v1/attendance/me/history', {
    query: { from_date: params.fromDate, to_date: params.toDate, page: params.page, page_size: params.pageSize },
    signal,
  })
}

/** MANAGER / TENANT_ADMIN only. */
export function getTeamToday(day?: string, signal?: AbortSignal): Promise<TeamAttendanceResponse> {
  return apiFetch<TeamAttendanceResponse>('/api/v1/attendance/team/today', { query: { day }, signal })
}

/** MANAGER / TENANT_ADMIN only. Cross-tenant or unknown ids both 404. */
export function getUserAttendance(
  userId: string,
  day?: string,
  signal?: AbortSignal,
): Promise<AttendanceTodayResponse> {
  return apiFetch<AttendanceTodayResponse>(`/api/v1/attendance/users/${userId}`, { query: { day }, signal })
}

export function getUserHistory(
  userId: string,
  params: HistoryQuery = {},
  signal?: AbortSignal,
): Promise<AttendanceHistoryResponse> {
  return apiFetch<AttendanceHistoryResponse>(`/api/v1/attendance/users/${userId}/history`, {
    query: { from_date: params.fromDate, to_date: params.toDate, page: params.page, page_size: params.pageSize },
    signal,
  })
}
