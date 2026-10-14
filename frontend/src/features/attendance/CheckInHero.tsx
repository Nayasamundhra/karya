/**
 * The employee home's reason for existing: check in/out is the page, not a
 * link off of it (see the redesign plan's diagnosis of the old HomePage).
 * This is the one dark, high-contrast surface on a signed-in screen (near-
 * black ink, a gold status label, a white pill action); everywhere else
 * colour stays restrained. It is ink in both light and dark mode on purpose —
 * a fixed brand surface, not a themed one.
 *
 * Still reads today's state from the backend's own `AttendanceTodayResponse`
 * exactly like `AttendanceStatusCard` does — no verdict is computed here,
 * only which of three backend-reported states to render and a live-ticking
 * clock (`useElapsedTime`) that is pure display arithmetic on a timestamp
 * the backend already returned.
 */
import { AlertTriangle, LogIn, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'

import { formatTime } from '@/features/attendance/formatters'
import { useElapsedTime } from '@/features/attendance/useElapsedTime'
import type { AttendanceTodayResponse } from '@/lib/api/types'

// A UI-only nicety, not an enforcement point: the real cutoff
// (`attendance_locations.max_shift_hours`, set per tenant) lives on the
// backend and this value is deliberately far below even the smallest
// reasonable one, so this warning appears well before any auto-close
// would happen - a nudge, never a prediction of one.
const LONG_SESSION_WARNING_HOURS = 10

export function CheckInHero({ today }: { today: AttendanceTodayResponse }) {
  const { day, state } = today
  const elapsed = useElapsedTime(state === 'CHECKED_IN' ? (day.first_check_in ?? null) : null)

  const checkedIn = state === 'CHECKED_IN'
  const completedToday = !checkedIn && day.status === 'COMPLETED'
  const elapsedHours = checkedIn && day.first_check_in ? hoursSince(day.first_check_in) : 0
  const isLongSession = checkedIn && elapsedHours >= LONG_SESSION_WARNING_HOURS

  return (
    <div className="relative flex flex-col gap-5 overflow-hidden rounded-3xl border border-white/10 bg-brand-ink p-6 text-white shadow-md sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-8">
      {/* Purely decorative — an ambient glow, not content, so it's hidden from AT. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-24 size-64 rounded-full bg-brand-purple/25 blur-3xl sm:size-80"
      />

      <div className="relative z-10 min-w-0">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-brand-gold">
          {checkedIn && <span aria-hidden="true" className="size-2 rounded-full bg-[#4ade80]" />}
          {checkedIn ? 'On the clock' : completedToday ? 'Today' : 'Ready when you are'}
        </div>

        {checkedIn && elapsed ? (
          <div
            className="mt-1.5 font-[family-name:var(--font-display)] text-4xl font-semibold tabular-nums leading-none tracking-tight sm:text-5xl lg:text-6xl"
            aria-live="off"
          >
            {elapsed}
          </div>
        ) : (
          <div className="mt-1.5 font-[family-name:var(--font-display)] text-2xl font-semibold leading-tight sm:text-3xl">
            {completedToday ? 'Attendance completed' : "You haven't checked in yet"}
          </div>
        )}

        <p className="mt-2.5 text-sm text-white/65 sm:text-base">{subtext(today)}</p>

        {isLongSession && (
          <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-brand-gold">
            <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
            Still checked in from earlier — forgot to check out?
          </p>
        )}
      </div>

      <Link
        to={checkedIn ? '/attendance/check-out' : '/attendance/check-in'}
        className="relative z-10 inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-full border border-white bg-white px-7 text-sm font-semibold text-brand-ink transition-colors hover:bg-transparent hover:text-white active:scale-[0.97] sm:h-13 sm:text-base"
      >
        {checkedIn ? (
          <>
            <LogOut className="size-5" aria-hidden="true" />
            Check Out
          </>
        ) : (
          <>
            <LogIn className="size-5" aria-hidden="true" />
            {completedToday ? 'Check In Again' : 'Check In'}
          </>
        )}
      </Link>
    </div>
  )
}

function hoursSince(isoTimestamp: string): number {
  return (Date.now() - new Date(isoTimestamp).getTime()) / (1000 * 60 * 60)
}

function subtext(today: AttendanceTodayResponse): string {
  const { day, state } = today
  if (state === 'CHECKED_IN' && day.first_check_in) {
    return `Checked in at ${formatTime(day.first_check_in)}`
  }
  if (day.status === 'COMPLETED' && day.first_check_in && day.last_check_out) {
    return `${formatTime(day.first_check_in)} – ${formatTime(day.last_check_out)}`
  }
  return 'Tap the button once you’re on site.'
}
