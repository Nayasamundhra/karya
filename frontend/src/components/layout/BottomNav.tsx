import { NavLink } from 'react-router-dom'

import { navItemsForRole } from '@/config/navigation'
import { roleNavClasses } from '@/config/roleAccent'
import { useAuth } from '@/features/auth/useAuth'
import { cn } from '@/lib/utils/cn'

/** Mobile only (`lg:hidden` — see AppShell). Fixed to the viewport bottom,
 * clear of the iOS home-indicator safe area via `env(safe-area-inset-bottom)`. */
export function BottomNav() {
  const { user } = useAuth()
  const items = navItemsForRole(user?.role).filter((item) => item.showInBottomNav)
  const { bottomNavActive } = roleNavClasses(user?.role)

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-surface-raised lg:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {items.map((item) => (
        <NavLink
          key={item.id}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-xs font-medium text-foreground-muted',
              isActive && bottomNavActive,
            )
          }
        >
          {({ isActive }: { isActive: boolean }) => (
            <>
              <item.icon className="size-5" aria-hidden="true" />
              <span>{item.label}</span>
              {isActive && <span className="sr-only"> (current page)</span>}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
