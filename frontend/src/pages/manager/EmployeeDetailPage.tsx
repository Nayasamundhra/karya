/**
 * One employee's attendance detail (§6/§7) — reached by clicking a row on
 * the team dashboard. Stays focused on attendance only, per the phase brief;
 * no per-employee analytics. A cross-tenant or unknown id both surface as
 * the same generic "not found" (§19/§23) — the backend already guarantees
 * this, `ErrorState`/`describeError` just render whatever it says.
 */
import { useParams } from 'react-router-dom'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/feedback/ErrorState'
import { EmployeeHistoryList } from '@/features/team/EmployeeHistoryList'
import { EmployeeStatusBadge } from '@/features/team/EmployeeStatusBadge'
import { formatTime } from '@/features/attendance/formatters'
import { useEmployeeAttendance } from '@/features/team/useEmployeeAttendance'

export default function EmployeeDetailPage() {
  const { userId } = useParams<{ userId: string }>()
  const { data, isPending, isError, error, refetch } = useEmployeeAttendance(userId ?? '')

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Employee attendance</h1>
        <p className="text-sm text-foreground-muted">Today's status and recent history for this employee.</p>
      </div>

      {isPending && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-56" />
          </CardContent>
        </Card>
      )}

      {isError && <ErrorState error={error} onRetry={refetch} />}

      {data && (
        <Card>
          <CardHeader>
            <CardTitle>{data.day.status === 'NO_RECORD' ? 'No attendance recorded today' : 'Today'}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <EmployeeStatusBadge status={data.day.status} />
            </div>
            {data.day.first_check_in && (
              <p className="text-sm text-foreground-muted">Checked in at {formatTime(data.day.first_check_in)}</p>
            )}
            {data.day.last_check_out && (
              <p className="text-sm text-foreground-muted">Checked out at {formatTime(data.day.last_check_out)}</p>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-foreground-muted">Employee history</h2>
        {userId && <EmployeeHistoryList userId={userId} />}
      </div>
    </div>
  )
}
