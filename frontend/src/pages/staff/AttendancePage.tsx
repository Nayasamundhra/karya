/**
 * The employee attendance home (§2). Deliberately light: today's state and
 * one obvious action up top, basic history below — no dashboard statistics,
 * no charts (Phase 10's job, not this one).
 */
import { AttendanceHistoryList } from '@/features/attendance/AttendanceHistoryList'
import { AttendanceStatusCard, AttendanceStatusCardSkeleton } from '@/features/attendance/AttendanceStatusCard'
import { useTodayAttendance } from '@/features/attendance/useTodayAttendance'
import { ErrorState } from '@/components/feedback/ErrorState'

export default function AttendancePage() {
  const { data: today, isPending, isError, error, refetch } = useTodayAttendance()

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Attendance</h1>
        <p className="text-sm text-foreground-muted">Today's status and your recent history.</p>
      </div>

      {isPending && <AttendanceStatusCardSkeleton />}
      {isError && <ErrorState error={error} onRetry={refetch} />}
      {today && <AttendanceStatusCard today={today} />}

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-foreground-muted">History</h2>
        <AttendanceHistoryList />
      </div>
    </div>
  )
}
