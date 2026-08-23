/**
 * Basic attendance history (§11) — a mobile-friendly card list rather than a
 * `Table` (see that component's own header comment: reserve `Table` for
 * genuinely tabular desktop data, and build a card list when phone-width
 * matters, which it does here first). No analytics, no charts — that's
 * Phase 10's job.
 */
import { useState } from 'react'
import { CalendarX2 } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatDay, formatTime } from '@/features/attendance/formatters'
import { useAttendanceHistory } from '@/features/attendance/useAttendanceHistory'
import type { AttendanceDayResponse } from '@/lib/api/types'

export function AttendanceHistoryList() {
  const [page, setPage] = useState(1)
  const { data, isPending, isError, error, refetch, isFetching } = useAttendanceHistory({ page })

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
        title="No attendance recorded yet"
        description="Your check-ins and check-outs will show up here."
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
        <StatusPill status={day.status} />
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

function StatusPill({ status }: { status: AttendanceDayResponse['status'] }) {
  const label = status === 'NO_RECORD' ? 'No record' : status === 'CHECKED_IN' ? 'Checked in' : 'Completed'
  const color =
    status === 'NO_RECORD'
      ? 'text-foreground-muted'
      : status === 'CHECKED_IN'
        ? 'text-success-700'
        : 'text-foreground-muted'
  return <span className={`text-xs font-medium ${color}`}>{label}</span>
}
