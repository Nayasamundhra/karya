/**
 * Hours worked across the tenant — split out from `TeamPage` so an employee
 * appears once per page for one job, not twice across two stacked sections.
 * Reachable from the sidebar's "Hours" item (desktop) and the mobile header
 * overflow menu — see `config/navigation.ts`.
 */
import { PageHeader } from '@/components/layout/PageHeader'
import { ErrorState } from '@/components/feedback/ErrorState'
import { TeamHoursCards, TeamHoursCardsSkeleton } from '@/features/team/TeamHoursCards'
import { TeamHoursChart } from '@/features/team/TeamHoursChart'
import { TeamHoursTable } from '@/features/team/TeamHoursTable'
import { useTeamHours } from '@/features/team/useTeamHours'

export default function TeamHoursPage() {
  const { data, isPending, isError, error, refetch } = useTeamHours()

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <PageHeader
        eyebrow="Hours worked"
        title="Team hours"
        description="An open shift counts up to now; it isn't final until the employee checks out."
      />

      {isPending && <TeamHoursCardsSkeleton />}
      {isError && <ErrorState error={error} onRetry={refetch} />}

      {data && (
        <>
          <TeamHoursCards summary={data.summary} />
          <TeamHoursChart employees={data.employees} />
          <TeamHoursTable employees={data.employees} />
        </>
      )}
    </div>
  )
}
