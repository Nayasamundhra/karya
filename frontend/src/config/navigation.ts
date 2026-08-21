/**
 * The one place navigation items and the roles allowed to see them are
 * declared. `AppShell` renders from this list rather than each component
 * hard-coding its own role check — see §8: "Do not hard-code role checks
 * throughout the application." Adding a Phase 9/10 screen means adding one
 * entry here, not touching the shell.
 */
import type { LucideIcon } from 'lucide-react'
import { CalendarClock, LayoutDashboard, User, Users } from 'lucide-react'

import { isUserRole, type UserRole } from '@/lib/api/types'

export interface NavItem {
  id: string
  label: string
  to: string
  icon: LucideIcon
  roles: readonly UserRole[]
  /** Shown in the mobile bottom nav (kept short — 4-5 items max fit comfortably). */
  showInBottomNav: boolean
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    id: 'home',
    label: 'Home',
    to: '/',
    icon: LayoutDashboard,
    roles: ['STAFF', 'MANAGER', 'TENANT_ADMIN'],
    showInBottomNav: true,
  },
  {
    id: 'attendance',
    label: 'Attendance',
    to: '/attendance',
    icon: CalendarClock,
    roles: ['STAFF', 'MANAGER', 'TENANT_ADMIN'],
    showInBottomNav: true,
  },
  {
    id: 'team',
    label: 'Team',
    to: '/team',
    icon: Users,
    roles: ['MANAGER', 'TENANT_ADMIN'],
    showInBottomNav: true,
  },
  {
    id: 'admin-users',
    label: 'Manage users',
    to: '/admin/users',
    icon: Users,
    roles: ['TENANT_ADMIN'],
    showInBottomNav: false,
  },
  {
    id: 'profile',
    label: 'Profile',
    to: '/profile',
    icon: User,
    roles: ['STAFF', 'MANAGER', 'TENANT_ADMIN'],
    showInBottomNav: true,
  },
] as const

/**
 * Takes the loose `string` the backend types `UserResponse.role` as (see
 * `app/schemas/user.py` — deliberately untyped there), not just `UserRole`,
 * so every call site can pass `user?.role` directly without its own
 * narrowing boilerplate.
 */
export function navItemsForRole(role: string | undefined): NavItem[] {
  if (!role || !isUserRole(role)) return []
  return NAV_ITEMS.filter((item) => item.roles.includes(role))
}
