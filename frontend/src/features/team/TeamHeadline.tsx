/**
 * "5 of 8 checked in" — the one number a manager actually opens this page
 * for, read straight from the backend's own `summary` (never recomputed
 * from `employees`, same discipline as `TeamSummaryCards`).
 */
import { Card, CardContent } from '@/components/ui/Card'
import type { TeamAttendanceResponse } from '@/lib/api/types'

const TIME_FORMAT: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }

export function TeamHeadline({ summary }: { summary: TeamAttendanceResponse['summary'] }) {
  const total = summary.total_staff
  const checkedIn = summary.checked_in
  const segments = Array.from({ length: Math.max(total, 1) }, (_, i) => i < checkedIn)

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:gap-6 sm:p-6">
        <div className="flex items-baseline gap-2">
          <span className="font-[family-name:var(--font-display)] text-5xl font-semibold leading-none tracking-tight text-manager-700 sm:text-6xl">
            {checkedIn}
          </span>
          <span className="text-lg text-foreground-muted">of {total} checked in</span>
        </div>

        <div className="flex flex-1 flex-wrap gap-1" role="img" aria-label={`${checkedIn} of ${total} employees checked in`}>
          {segments.map((filled, i) => (
            <span
              key={i}
              aria-hidden="true"
              className={filled ? 'h-2.5 w-7 rounded-full bg-manager-500' : 'h-2.5 w-7 rounded-full bg-border'}
            />
          ))}
        </div>

        <span className="shrink-0 text-xs text-foreground-muted sm:self-end">
          as of {new Date().toLocaleTimeString(undefined, TIME_FORMAT)}
        </span>
      </CardContent>
    </Card>
  )
}
