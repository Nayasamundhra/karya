import { Menu } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu'
import { UserMenu } from '@/components/layout/UserMenu'
import { navItemsForRole } from '@/config/navigation'
import { useAuth } from '@/features/auth/useAuth'
import { useTenant } from '@/features/tenant/useTenant'
import { Skeleton } from '@/components/ui/Skeleton'

/**
 * The one header, used on every breakpoint. On mobile it also carries the
 * overflow menu for nav items that don't fit the bottom bar (e.g. "Manage
 * users") — see `Sidebar`/`BottomNav` for why those two are split instead of
 * one component trying to be both.
 */
export function Header() {
  const { user } = useAuth()
  const { data: tenant, isLoading: isTenantLoading } = useTenant()
  const navigate = useNavigate()
  const overflowItems = navItemsForRole(user?.role).filter((item) => !item.showInBottomNav)

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
      <div className="flex items-center gap-2">
        {overflowItems.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label="More navigation"
              className="flex size-11 items-center justify-center rounded-md text-foreground hover:bg-surface-sunken lg:hidden"
            >
              <Menu className="size-5" aria-hidden="true" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {overflowItems.map((item) => (
                <DropdownMenuItem key={item.id} onSelect={() => navigate(item.to)}>
                  <item.icon className="size-4" aria-hidden="true" />
                  {item.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <span className="text-sm font-medium text-foreground-muted">
          {isTenantLoading ? <Skeleton className="h-4 w-24" /> : tenant?.name}
        </span>
      </div>
      <UserMenu />
    </header>
  )
}
