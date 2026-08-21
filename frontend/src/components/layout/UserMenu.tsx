import { ChevronDown, LogOut, User as UserIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu'
import { useAuth } from '@/features/auth/useAuth'
import { toast } from '@/stores/toastStore'

export function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    toast.info('Signed out')
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex min-h-11 items-center gap-2 rounded-md px-2 text-sm font-medium text-foreground hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="flex size-7 items-center justify-center rounded-full bg-accent-100 text-xs font-semibold text-accent-700">
          {user.name.slice(0, 1).toUpperCase()}
        </span>
        <span className="hidden sm:inline">{user.name}</span>
        <ChevronDown className="size-4 text-foreground-muted" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          {user.name}
          <div className="font-normal text-foreground-muted">{user.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate('/profile')}>
          <UserIcon className="size-4" aria-hidden="true" />
          Profile
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem destructive onSelect={handleLogout}>
          <LogOut className="size-4" aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
