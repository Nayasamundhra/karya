import { NavLink } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import { navItemsForRole } from '@/config/navigation'
import { roleNavClasses } from '@/config/roleAccent'
import { cn } from '@/lib/utils/cn'

/** Desktop only (`hidden lg:flex` — see AppShell). Mobile uses `BottomNav` +
 * the overflow menu in `MobileHeader` instead of shrinking this. */
export function Sidebar() {
  const { user } = useAuth()
  const items = navItemsForRole(user?.role)
  const { sidebarActive } = roleNavClasses(user?.role)

  return (
    <nav
      aria-label="Primary"
      className="hidden w-60 shrink-0 flex-col gap-1 border-r border-border bg-surface-raised p-4 lg:flex"
    >
      <div className="mb-4 flex items-center gap-2 px-2">
        <span className="flex size-8 items-center justify-center rounded-md bg-accent-600 text-sm font-bold text-white">
          K
        </span>
        <span className="text-base font-semibold text-foreground">Karya</span>
      </div>
      {items.map((item) => (
        <NavLink
          key={item.id}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium text-foreground-muted hover:bg-surface-sunken hover:text-foreground',
              isActive && sidebarActive,
            )
          }
        >
          <item.icon className="size-4 shrink-0" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}
