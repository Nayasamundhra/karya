/**
 * "5 of 8 checked in" — the one number a manager actually opens this page
 * for, read straight from the backend's own `summary` (never recomputed
 * from `employees`, same discipline as `TeamSummaryCards`). Also carries
 * the "Generate display QR" shortcut: MANAGER is one of the backend's
 * `QR_ISSUER_ROLES`, and `/admin/organization` is exactly where that role
 * lands on the Displays screen (see `OrganizationPage.tsx`) — this closes
 * the loop from "I need a QR up" to "here it is" in one click instead of
 * hunting for where display management lives.
 */
import { MonitorSmartphone } from 'lucide-react'
import { Link } from 'react-router-dom'

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
          <span className="font-[family-name:var(--font-display)] text-4xl font-bold text-manager-700 sm:text-5xl">
            {checkedIn}
          </span>
          <span className="text-lg text-foreground-muted">of {total} checked in</span>
        </div>

        <div className="flex flex-1 flex-wrap gap-1" role="img" aria-label={`${checkedIn} of ${total} employees checked in`}>
          {segments.map((filled, i) => (
            <span
              key={i}
              aria-hidden="true"
              className={filled ? 'h-2.5 w-7 rounded-sm bg-manager-500' : 'h-2.5 w-7 rounded-sm bg-border'}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end sm:justify-start sm:gap-2">
          <span className="text-xs text-foreground-muted">
            as of {new Date().toLocaleTimeString(undefined, TIME_FORMAT)}
          </span>
          <Link
            to="/admin/organization?tab=displays"
            className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-manager-500 px-4 text-sm font-semibold text-manager-700 transition-colors hover:bg-manager-50"
          >
            <MonitorSmartphone className="size-4" aria-hidden="true" />
            Generate display QR
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}
