/**
 * The redesign's "role atmosphere": one accent hue per signed-in role,
 * spent only on section chrome (the active nav item, a headline stat, a
 * card's icon tile) — never a large fill. `Sidebar`/`BottomNav` use this so
 * the one piece of chrome every authenticated screen shares (which nav item
 * is active) already identifies "whose app this is" before the page's own
 * content does.
 *
 * Full static class strings, not `` `bg-${role}-50` `` — Tailwind's
 * build-time scanner needs the literal class name to appear somewhere in
 * source to keep it out of the production build's purge.
 */
import type { UserRole } from '@/lib/api/types'

export interface RoleNavClasses {
  /** Sidebar's active `NavLink` — background, text, and the hover variants
   * of both, so hovering an already-active item doesn't flash back to the
   * generic hover style. */
  sidebarActive: string
  /** BottomNav's active `NavLink` text (no background there — see BottomNav.tsx). */
  bottomNavActive: string
}

const ROLE_NAV_CLASSES: Record<UserRole, RoleNavClasses> = {
  STAFF: {
    sidebarActive: 'bg-employee-50 text-employee-700 hover:bg-employee-50 hover:text-employee-700',
    bottomNavActive: 'text-employee-700',
  },
  MANAGER: {
    sidebarActive: 'bg-manager-50 text-manager-700 hover:bg-manager-50 hover:text-manager-700',
    bottomNavActive: 'text-manager-700',
  },
  TENANT_ADMIN: {
    sidebarActive: 'bg-admin-50 text-admin-700 hover:bg-admin-50 hover:text-admin-700',
    bottomNavActive: 'text-admin-700',
  },
  // No dedicated color for a platform role with no screens of its own yet
  // (see HomePage.tsx) — falls back to the neutral core accent.
  SUPER_ADMIN: {
    sidebarActive: 'bg-accent-50 text-accent-700 hover:bg-accent-50 hover:text-accent-700',
    bottomNavActive: 'text-accent-600',
  },
}

const FALLBACK: RoleNavClasses = {
  sidebarActive: 'bg-accent-50 text-accent-700 hover:bg-accent-50 hover:text-accent-700',
  bottomNavActive: 'text-accent-600',
}

export function roleNavClasses(role: string | undefined): RoleNavClasses {
  if (!role || !(role in ROLE_NAV_CLASSES)) return FALLBACK
  return ROLE_NAV_CLASSES[role as UserRole]
}
