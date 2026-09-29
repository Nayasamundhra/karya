import { Card, CardContent } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
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
    <div role="group" aria-label="Team hours worked" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="flex flex-col gap-1 p-4">
            <p className="text-2xl font-semibold text-foreground">{formatHours(card.value)}</p>
            <p className="text-xs font-medium text-foreground-muted">{card.label}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function TeamHoursCardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => (
        <Card key={i}>
          <CardContent className="flex flex-col gap-2 p-4">
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-24" />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
