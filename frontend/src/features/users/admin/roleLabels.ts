import type { UserRole } from '@/lib/api/types'

/** Product-facing role labels (§9: "Employee", never "Staff") — the one
 * place this mapping is defined, shared by the create form, the role-change
 * dialog, and the employee table. SUPER_ADMIN is included only so a stray
 * value never renders blank; the tenant-admin UI never assigns it. */
export const ROLE_LABEL: Record<UserRole, string> = {
  SUPER_ADMIN: 'Super Admin',
  TENANT_ADMIN: 'Tenant Admin',
  MANAGER: 'Manager',
  STAFF: 'Employee',
}

export function roleLabel(role: string): string {
  return ROLE_LABEL[role as UserRole] ?? role
}
