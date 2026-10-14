import { Link, NavLink } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import { BrandMark } from '@/features/marketing/BrandMark'
import { navItemsForRole } from '@/config/navigation'
import { roleNavClasses } from '@/config/roleAccent'
import { cn } from '@/lib/utils/cn'
import { roleLabel } from '@/lib/utils/roleLabel'

/** Desktop only (`hidden lg:flex` — see AppShell). Mobile uses `BottomNav` +
 * the overflow menu in `MobileHeader` instead of shrinking this. */
export function Sidebar() {
  const { user } = useAuth()
  const items = navItemsForRole(user?.role)
  const { sidebarActive } = roleNavClasses(user?.role)

  return (
    <nav
      aria-label="Primary"
      className="hidden w-64 shrink-0 flex-col gap-1 border-r border-border bg-surface-raised p-4 lg:flex"
    >
      <BrandMark className="mb-6 px-2 pt-2 text-foreground" />
      {items.map((item) => (
        <NavLink
          key={item.id}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex min-h-11 items-center gap-3 rounded-xl px-3.5 text-[15px] font-medium text-foreground-muted transition-colors hover:bg-surface-sunken hover:text-foreground',
              isActive && sidebarActive,
            )
          }
        >
          <item.icon className="size-5 shrink-0" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}

      {user && (
        <Link
          to="/profile"
          className="mt-auto flex items-center gap-3 rounded-xl border-t border-border px-2 pb-1 pt-4 hover:bg-surface-sunken"
        >
          <span
            aria-hidden="true"
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent-100 text-sm font-semibold text-accent-700"
          >
            {user.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold text-foreground">{user.name}</span>
            <span className="truncate text-xs text-foreground-muted">{roleLabel(user.role)}</span>
          </span>
        </Link>
      )}
    </nav>
  )
}
