/**
 * Today's attendance state, front and center — §2 ("Employee Home"). The
 * three states rendered here are the backend's own `DayStatus`
 * (`NO_RECORD` / `CHECKED_IN` / `COMPLETED`), not something invented on the
 * client. The primary action, though, is gated on `state`
 * (`AttendanceTodayResponse.state`, the two-value `NOT_CHECKED_IN` /
 * `CHECKED_IN` machine) rather than `day.status` — a `COMPLETED` day still
 * leaves the caller `NOT_CHECKED_IN`, and the backend's attendance model
 * allows a second check-in the same day (a lunch break, a second shift), so
 * this doesn't block that even though it isn't the headline flow.
 */
import { CheckCircle2, LogIn, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatTime } from '@/features/attendance/formatters'
import type { AttendanceTodayResponse } from '@/lib/api/types'

export function AttendanceStatusCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-56" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-11 w-full" />
      </CardContent>
    </Card>
  )
}

export function AttendanceStatusCard({ today }: { today: AttendanceTodayResponse }) {
  const { day, state } = today

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        {/* `aria-live="polite"` — §18: a check-in/check-out that returns here
         * (via query invalidation) must announce the new state to a screen
         * reader without the caller needing to re-focus anything. */}
        <div aria-live="polite" className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <StatusBadge status={day.status} />
          </div>
          <p className="text-lg font-semibold text-foreground">{headline(day.status)}</p>
          {subtext(day) && <p className="text-sm text-foreground-muted">{subtext(day)}</p>}
        </div>

        {state === 'NOT_CHECKED_IN' && (
          <Button asChild size="lg" variant={day.status === 'COMPLETED' ? 'secondary' : 'primary'}>
            <Link to="/attendance/check-in">
              <LogIn className="size-5" aria-hidden="true" />
              {day.status === 'COMPLETED' ? 'Check in again' : 'Check in'}
            </Link>
          </Button>
        )}

        {state === 'CHECKED_IN' && (
          <Button asChild size="lg" variant="primary">
            <Link to="/attendance/check-out">
              <LogOut className="size-5" aria-hidden="true" />
              Check out
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

function StatusBadge({ status }: { status: AttendanceTodayResponse['day']['status'] }) {
  switch (status) {
    case 'CHECKED_IN':
      return <Badge variant="success">Checked in</Badge>
    case 'COMPLETED':
      return <Badge variant="neutral">Completed</Badge>
    case 'NO_RECORD':
    default:
      return <Badge variant="warning">Not checked in</Badge>
  }
}

function headline(status: AttendanceTodayResponse['day']['status']): string {
  switch (status) {
    case 'CHECKED_IN':
      return "You're checked in"
    case 'COMPLETED':
      return 'Attendance completed'
    case 'NO_RECORD':
    default:
      return 'Not checked in'
  }
}

function subtext(day: AttendanceTodayResponse['day']): string | null {
  if (day.status === 'CHECKED_IN' && day.first_check_in) {
    return `Checked in at ${formatTime(day.first_check_in)}`
  }
  if (day.status === 'COMPLETED' && day.first_check_in && day.last_check_out) {
    return `${formatTime(day.first_check_in)} – ${formatTime(day.last_check_out)}`
  }
  return null
}

/** Exported for the success screen (§10), which wants the same "done" iconography. */
export const AttendanceCompleteIcon = CheckCircle2
