import { CalendarClock, UserCog, Users } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { useAuth } from '@/features/auth/useAuth'
import type { UserRole } from '@/lib/api/types'

const NEXT_STEP: Record<UserRole, { icon: typeof CalendarClock; text: string }> = {
  STAFF: { icon: CalendarClock, text: 'Check in and out, and see your attendance history, from Attendance.' },
  MANAGER: { icon: Users, text: "Your team's attendance overview will appear here once Phase 10 ships." },
  TENANT_ADMIN: { icon: UserCog, text: 'Full user and organization management will appear here once Phase 10 ships.' },
  SUPER_ADMIN: { icon: UserCog, text: 'Platform administration is not part of Karya yet.' },
}

/**
 * A deliberately light landing page. The real per-role dashboards are
 * Phase 9 (employee attendance) and Phase 10 (manager/admin) — see
 * CLAUDE.md. This still answers §38's "where am I / what's my status /
 * what's next" for the one thing Phase 8 actually knows: who signed in, and
 * what role they hold.
 */
export default function HomePage() {
  const { user } = useAuth()
  if (!user) return null

  const role = isKnownRole(user.role) ? user.role : 'STAFF'
  const next = NEXT_STEP[role]

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Welcome, {user.name}</h1>
        <p className="text-sm text-foreground-muted">
          Signed in as {roleLabel(role)} · {user.employee_code}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>What's next</CardTitle>
          <CardDescription>{next.text}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 rounded-md bg-surface-sunken p-4 text-sm text-foreground-muted">
            <next.icon className="size-5 shrink-0" aria-hidden="true" />
            <span>This foundation (Phase 8) wires up auth, navigation, and the design system these screens will use.</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function isKnownRole(role: string): role is UserRole {
  return role in NEXT_STEP
}

function roleLabel(role: UserRole): string {
  switch (role) {
    case 'TENANT_ADMIN':
      return 'Tenant Admin'
    case 'MANAGER':
      return 'Manager'
    case 'STAFF':
      // Product-facing terminology says "Employee", not "Staff" (CLAUDE.md) —
      // the `STAFF` role identifier itself is the backend's, left unchanged.
      return 'Employee'
    case 'SUPER_ADMIN':
      return 'Super Admin'
  }
}
