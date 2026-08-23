/** Centralized TanStack Query keys for tenant-admin employee management
 * (Phase 10) — mirrors the pattern in `features/attendance/queryKeys.ts` and
 * `features/team/queryKeys.ts`. */
import type { ListUsersQuery } from '@/lib/api/endpoints/users'

export const adminUserKeys = {
  all: ['admin', 'users'] as const,
  list: (params: ListUsersQuery = {}) => [...adminUserKeys.all, 'list', params] as const,
}
