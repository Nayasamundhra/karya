/**
 * One employee's attendance history (§7) — the same card-list pattern as
 * the self-service `AttendanceHistoryList` (Phase 9), addressed by id
 * instead of "me". Kept as its own small component rather than
 * parameterizing the Phase 9 one, so that tested staff-facing code is never
 * touched by this phase (see CLAUDE.md).
 */
import { useState } from 'react'
import { CalendarX2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmployeeStatusBadge } from '@/features/team/EmployeeStatusBadge'
import { formatDay, formatTime } from '@/features/attendance/formatters'
import { useEmployeeHistory } from '@/features/team/useEmployeeAttendance'
import type { AttendanceDayResponse } from '@/lib/api/types'

export function EmployeeHistoryList({ userId }: { userId: string }) {
  const [page, setPage] = useState(1)
  const { data, isPending, isError, error, refetch, isFetching } = useEmployeeHistory(userId, { page })

  if (isPending) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    )
  }

  if (isError) {
    return <ErrorState error={error} onRetry={refetch} />
  }

  if (data.items.length === 0) {
    return (
      <EmptyState
        icon={CalendarX2}
        title="No attendance history available"
        description="This employee's check-ins and check-outs will show up here."
      />
    )
  }

  const { pagination } = data

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {data.items.map((day) => (
          <li key={day.date}>
            <DayRow day={day} />
          </li>
        ))}
      </ul>

      {pagination.total_pages > 1 && (
        <nav aria-label="History pages" className="flex items-center justify-between pt-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={pagination.page <= 1 || isFetching}
            onClick={() => setPage(pagination.page - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-foreground-muted">
            Page {pagination.page} of {pagination.total_pages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={pagination.page >= pagination.total_pages || isFetching}
            onClick={() => setPage(pagination.page + 1)}
          >
            Next
          </Button>
        </nav>
      )}
    </div>
  )
}

function DayRow({ day }: { day: AttendanceDayResponse }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div>
          <p className="text-sm font-medium text-foreground">{formatDay(day.date)}</p>
          <p className="text-xs text-foreground-muted">{sessionsSummary(day)}</p>
        </div>
        <EmployeeStatusBadge status={day.status} />
      </CardContent>
    </Card>
  )
}

function sessionsSummary(day: AttendanceDayResponse): string {
  if (day.status === 'NO_RECORD') return 'No record'
  const checkIn = day.first_check_in ? formatTime(day.first_check_in) : '—'
  const checkOut = day.last_check_out ? formatTime(day.last_check_out) : '—'
  return `${checkIn} – ${checkOut}`
}
