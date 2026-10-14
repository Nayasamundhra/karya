import { StatCard, StatCardGrid, StatCardGridSkeleton } from '@/components/ui/StatCard'
import { formatHours } from '@/features/attendance/formatters'
import type { TeamHoursResponse } from '@/lib/api/types'

/** Team-wide hours worked (§ hours-worked addition) — read verbatim from the
 * backend's `summary`, never summed from `employees` client-side, same
 * discipline as `TeamSummaryCards`. An open session's contribution is
 * computed by the backend up to the moment of the request, so these numbers
 * move on their own between polls (see `useTeamHours`'s refetch interval)
 * without anything writing to them. */
export function TeamHoursCards({ summary }: { summary: TeamHoursResponse['summary'] }) {
  const cards = [
    { label: 'Hours Today', value: summary.total_today_hours },
    { label: 'Hours This Week', value: summary.total_week_hours },
    { label: 'Hours This Month', value: summary.total_month_hours },
  ]

  return (
    <StatCardGrid ariaLabel="Team hours worked" columns={3}>
      {cards.map((card) => (
        <StatCard key={card.label} label={card.label} value={formatHours(card.value)} hue="manager" />
      ))}
    </StatCardGrid>
  )
}

export function TeamHoursCardsSkeleton() {
  return <StatCardGridSkeleton count={3} columns={3} />
}
