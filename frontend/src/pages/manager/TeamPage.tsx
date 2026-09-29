/**
 * The manager/tenant-admin dashboard (§3–§5) — today's attendance across the
 * tenant, front and center. Originally scoped as deliberately operational,
 * not analytical (see CLAUDE.md's Phase 10 non-goals) — the hours-worked
 * section below is a since-confirmed exception to that, not an oversight;
 * it stays a plain running total, not a chart or trend line. Two requests
 * back this page: `GET /attendance/team/today` and `GET /attendance/team/hours`,
 * loaded and shown independently so a slow one never blocks the other.
 */
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { TeamAttendanceTable } from '@/features/team/TeamAttendanceTable'
import { TeamHeadline } from '@/features/team/TeamHeadline'
import { TeamHoursCards, TeamHoursCardsSkeleton } from '@/features/team/TeamHoursCards'
import { TeamHoursTable } from '@/features/team/TeamHoursTable'
import { TeamSummaryCards, TeamSummaryCardsSkeleton } from '@/features/team/TeamSummaryCards'
import { useTeamHours } from '@/features/team/useTeamHours'
import { useTeamToday } from '@/features/team/useTeamToday'

export default function TeamPage() {
  const today = useTeamToday()
  const hours = useTeamHours()

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Team attendance</h1>
        <p className="text-sm text-foreground-muted">Who's working today, and how far along they are.</p>
      </div>

      {today.isPending && (
        <>
          <Skeleton className="h-24 w-full rounded-lg" />
          <TeamSummaryCardsSkeleton />
        </>
      )}
      {today.isError && <ErrorState error={today.error} onRetry={today.refetch} />}

      {today.data && (
        <>
          <TeamHeadline summary={today.data.summary} />
          <TeamSummaryCards summary={today.data.summary} />
          <TeamAttendanceTable employees={today.data.employees} />
        </>
      )}

      <div className="flex flex-col gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Hours worked</h2>
          <p className="text-sm text-foreground-muted">
            An open shift counts up to now; it isn't final until the employee checks out.
          </p>
        </div>

        {hours.isPending && <TeamHoursCardsSkeleton />}
        {hours.isError && <ErrorState error={hours.error} onRetry={hours.refetch} />}

        {hours.data && (
          <>
            <TeamHoursCards summary={hours.data.summary} />
            <TeamHoursTable employees={hours.data.employees} />
          </>
        )}
      </div>
    </div>
  )
}
