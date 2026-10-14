import type { UserRole } from '@/lib/api/types'

/**
 * Product-facing role names. "Employee", not "Staff": that is the term the
 * product uses everywhere user-visible (CLAUDE.md) — the `STAFF` identifier
 * is the backend's own and stays as is. Takes a loose `string` because
 * `UserResponse.role` is deliberately untyped on the backend schema.
 */
export function roleLabel(role: UserRole | string | undefined): string {
  switch (role) {
    case 'TENANT_ADMIN':
      return 'Admin'
    case 'MANAGER':
      return 'Manager'
    case 'STAFF':
      return 'Employee'
    case 'SUPER_ADMIN':
      return 'Super admin'
    default:
      return ''
  }
}
