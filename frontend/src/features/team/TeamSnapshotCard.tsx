import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Card, CardContent } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatHours } from '@/features/attendance/formatters'
import { useTeamHours } from '@/features/team/useTeamHours'
import { useTeamToday } from '@/features/team/useTeamToday'

/**
 * A light pointer on the manager/tenant-admin Home page toward the two full
 * dashboards (`/team`, `/team/hours`) — not a second dashboard. Deliberately
 * smaller/quieter than either page's own cards: one line for today's
 * headcount, one line for hours, both linking out to the real view. On
 * error it just doesn't render, same as `WeekOverview`'s own supplementary
 * chart — a failed fetch here shouldn't crowd Home with a second error
 * banner under the "what's next" card above it.
 */
export function TeamSnapshotCard() {
  const today = useTeamToday()
  const hours = useTeamHours()

  if (today.isError || hours.isError) return null

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-foreground">Team snapshot</h2>
      <Card>
        <CardContent className="flex flex-col divide-y divide-border p-0">
          <SnapshotRow
            isPending={today.isPending}
            to="/team"
            linkLabel="View team"
            text={today.data ? `${today.data.summary.checked_in} of ${today.data.summary.total_staff} checked in today` : undefined}
          />
          <SnapshotRow
            isPending={hours.isPending}
            to="/team/hours"
            linkLabel="View hours"
            text={
              hours.data
                ? `${formatHours(hours.data.summary.total_today_hours)} today · ${formatHours(hours.data.summary.total_week_hours)} this week`
                : undefined
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}

function SnapshotRow({
  isPending,
  text,
  to,
  linkLabel,
}: {
  isPending: boolean
  text: string | undefined
  to: string
  linkLabel: string
}) {
  return (
    <div className="flex items-center justify-between gap-3 p-4">
      {isPending || !text ? (
        <Skeleton className="h-4 w-40" />
      ) : (
        <p className="truncate text-sm text-foreground">{text}</p>
      )}
      <Link
        to={to}
        className="flex shrink-0 items-center gap-1 text-sm font-medium text-manager-700 hover:text-manager-600"
      >
        {linkLabel}
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </div>
  )
}
