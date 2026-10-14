/**
 * The manager/tenant-admin dashboard (§3–§5) — today's attendance across the
 * tenant, front and center. Attendance-only: hours worked lives on its own
 * page (`TeamHoursPage`, `/team/hours`) rather than stacked below this one —
 * the two used to share a page and show the same employees twice, once per
 * section, which read as redundant rather than thorough.
 */
import { PageHeader } from '@/components/layout/PageHeader'
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
      <PageHeader eyebrow="Today" title="Team attendance" description="Who's working today, and how far along they are." />

      {isPending && (
        <>
          <Skeleton className="h-24 w-full rounded-3xl" />
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
