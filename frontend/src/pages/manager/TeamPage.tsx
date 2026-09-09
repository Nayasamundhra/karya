/**
 * The manager/tenant-admin dashboard (§3–§5) — today's attendance across the
 * tenant, front and center. Deliberately operational, not analytical: no
 * charts, no trends, just "who's working today" (see CLAUDE.md's Phase 10
 * non-goals). A single `GET /attendance/team/today` request backs the whole
 * page; filtering and navigation to an employee's detail happen client-side.
 */
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { TeamAttendanceTable } from '@/features/team/TeamAttendanceTable'
import { TeamHeadline } from '@/features/team/TeamHeadline'
import { TeamSummaryCards, TeamSummaryCardsSkeleton } from '@/features/team/TeamSummaryCards'
import { useTeamToday } from '@/features/team/useTeamToday'

export default function TeamPage() {
  const { data, isPending, isError, error, refetch } = useTeamToday()

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Team attendance</h1>
        <p className="text-sm text-foreground-muted">Who's working today, and how far along they are.</p>
      </div>

      {isPending && (
        <>
          <Skeleton className="h-24 w-full rounded-lg" />
          <TeamSummaryCardsSkeleton />
        </>
      )}
      {isError && <ErrorState error={error} onRetry={refetch} />}

      {data && (
        <>
          <TeamHeadline summary={data.summary} />
          <TeamSummaryCards summary={data.summary} />
          <TeamAttendanceTable employees={data.employees} />
        </>
      )}
    </div>
  )
}
