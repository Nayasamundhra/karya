import { StatCard, StatCardGrid, StatCardGridSkeleton } from '@/components/ui/StatCard'
import type { TeamAttendanceResponse } from '@/lib/api/types'

/** The four counts a manager needs at a glance (§3) — read verbatim from the
 * backend's `summary` object, never recomputed from `employees` client-side,
 * so this can never drift from what the table below shows. */
export function TeamSummaryCards({ summary }: { summary: TeamAttendanceResponse['summary'] }) {
  const cards = [
    { label: 'Total Employees', value: summary.total_staff },
    { label: 'Checked In', value: summary.checked_in },
    { label: 'Completed', value: summary.completed },
    { label: 'No Record', value: summary.no_record },
  ]

  return (
    <StatCardGrid ariaLabel="Team summary">
      {cards.map((card) => (
        <StatCard key={card.label} label={card.label} value={String(card.value)} hue="manager" />
      ))}
    </StatCardGrid>
  )
}

export function TeamSummaryCardsSkeleton() {
  return <StatCardGridSkeleton count={4} />
}
