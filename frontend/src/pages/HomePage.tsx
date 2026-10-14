import { PageHeader } from '@/components/layout/PageHeader'
import { UserCog, Users } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { EmployeeHome } from '@/features/attendance/EmployeeHome'
import { useAuth } from '@/features/auth/useAuth'
import { useSetupStatus } from '@/features/onboarding/useSetupStatus'
import { TeamSnapshotCard } from '@/features/team/TeamSnapshotCard'
import type { UserRole } from '@/lib/api/types'
import { roleLabel } from '@/lib/utils/roleLabel'

/** STAFF is handled by `EmployeeHome` below — it has an actual job on this
 * page (check in/out), not a pointer to one, so it isn't part of this map. */
type PointerRole = Exclude<UserRole, 'STAFF'>

interface NextStep {
  icon: typeof UserCog
  text: string
  /** Omitted for a role with genuinely nothing to link to yet (SUPER_ADMIN). */
  to?: string
  cta?: string
}

const NEXT_STEP: Record<PointerRole, NextStep> = {
  MANAGER: {
    icon: Users,
    text: "See who's checked in today across your team.",
    to: '/team',
    cta: 'Go to Team',
  },
  TENANT_ADMIN: {
    icon: UserCog,
    text: 'Manage employees and your organization settings.',
    to: '/admin/users',
    cta: 'Manage employees',
  },
  SUPER_ADMIN: { icon: UserCog, text: 'Platform administration is not part of Karya yet.' },
}

const KNOWN_ROLES: readonly UserRole[] = ['STAFF', 'MANAGER', 'TENANT_ADMIN', 'SUPER_ADMIN']

export default function HomePage() {
  const { user } = useAuth()
  if (!user) return null

  const role = isKnownRole(user.role) ? user.role : 'STAFF'

  if (role === 'STAFF') {
    return <EmployeeHome name={user.name} />
  }

  const next = NEXT_STEP[role]

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <PageHeader eyebrow={`${roleLabel(role)} · ${user.employee_code}`} title={`Welcome, ${user.name}.`} />
      {role === 'TENANT_ADMIN' && <SetupNudge />}
      <Card>
        <CardHeader>
          <CardTitle>What's next</CardTitle>
          <CardDescription>{next.text}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-3 rounded-2xl bg-surface-sunken p-4 text-sm text-foreground-muted">
            <div className="flex items-center gap-3">
              <next.icon className="size-5 shrink-0" aria-hidden="true" />
              <span>{next.text}</span>
            </div>
            {next.to && next.cta && (
              <Button asChild size="sm">
                <Link to={next.to}>{next.cta}</Link>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
      {(role === 'MANAGER' || role === 'TENANT_ADMIN') && <TeamSnapshotCard />}
    </div>
  )
}

/**
 * §6: "Do not show empty dashboards with confusing zeroes when setup has
 * not been completed." Rather than let Home quietly show a Team/Users page
 * with nothing in it, a tenant admin with an unfinished setup sees exactly
 * what's left and where to go — nothing renders once every step is done.
 */
function SetupNudge() {
  const { isLoading, isComplete } = useSetupStatus()
  if (isLoading || isComplete) return null

  return (
    <Alert variant="info" title="Finish setting up your organization">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>A few steps remain before employees can check in or out.</span>
        <Button asChild size="sm" variant="secondary">
          <Link to="/setup">View checklist</Link>
        </Button>
      </div>
    </Alert>
  )
}

function isKnownRole(role: string): role is UserRole {
  return (KNOWN_ROLES as readonly string[]).includes(role)
}
