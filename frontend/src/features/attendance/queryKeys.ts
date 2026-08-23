/**
 * Centralized TanStack Query keys for attendance data — the single place
 * check-in/check-out invalidate after a successful mutation (§17), so a new
 * query call site can never drift from what the mutations invalidate.
 */
import type { HistoryQuery } from '@/lib/api/endpoints/attendance'

export const attendanceKeys = {
  all: ['attendance'] as const,
  today: (day?: string) => [...attendanceKeys.all, 'today', day ?? 'current'] as const,
  history: (params: HistoryQuery = {}) => [...attendanceKeys.all, 'history', params] as const,
}
