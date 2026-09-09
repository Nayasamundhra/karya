import { Card, CardContent } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
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
    <div role="group" aria-label="Team summary" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="flex flex-col gap-1 p-4">
            <p className="text-2xl font-semibold text-foreground">{card.value}</p>
            <p className="text-xs font-medium text-foreground-muted">{card.label}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function TeamSummaryCardsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {Array.from({ length: 4 }, (_, i) => (
        <Card key={i}>
          <CardContent className="flex flex-col gap-2 p-4">
            <Skeleton className="h-8 w-12" />
            <Skeleton className="h-3 w-20" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
