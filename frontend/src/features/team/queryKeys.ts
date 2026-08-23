/**
 * Centralized TanStack Query keys for the manager/admin team-attendance
 * views (Phase 10) — mirrors `features/attendance/queryKeys.ts`'s pattern so
 * there is exactly one place each of these queries is keyed.
 */
import type { HistoryQuery } from '@/lib/api/endpoints/attendance'

export const teamKeys = {
  all: ['team'] as const,
  today: (day?: string) => [...teamKeys.all, 'today', day ?? 'current'] as const,
  member: (userId: string, day?: string) => [...teamKeys.all, 'member', userId, day ?? 'current'] as const,
  memberHistory: (userId: string, params: HistoryQuery = {}) =>
    [...teamKeys.all, 'member', userId, 'history', params] as const,
}
