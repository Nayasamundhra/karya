/**
 * The employee home's reason for existing: check in/out is the page, not a
 * link off of it (see the redesign plan's diagnosis of the old HomePage).
 * This is the one place — alongside the kiosk display — the gradient
 * "spotlight" surface is allowed to appear (`styles/index.css`'s
 * `--color-spotlight-*`); everywhere else color stays restrained.
 *
 * Still reads today's state from the backend's own `AttendanceTodayResponse`
 * exactly like `AttendanceStatusCard` does — no verdict is computed here,
 * only which of three backend-reported states to render and a live-ticking
 * clock (`useElapsedTime`) that is pure display arithmetic on a timestamp
 * the backend already returned.
 */
import { LogIn, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'

import { formatTime } from '@/features/attendance/formatters'
import { useElapsedTime } from '@/features/attendance/useElapsedTime'
import type { AttendanceTodayResponse } from '@/lib/api/types'

export function CheckInHero({ today }: { today: AttendanceTodayResponse }) {
  const { day, state } = today
  const elapsed = useElapsedTime(state === 'CHECKED_IN' ? (day.first_check_in ?? null) : null)

  const checkedIn = state === 'CHECKED_IN'
  const completedToday = !checkedIn && day.status === 'COMPLETED'

  return (
    <div
      className="relative flex flex-col gap-5 overflow-hidden rounded-2xl p-6 text-white sm:flex-row sm:items-center sm:justify-between sm:gap-6 sm:p-8"
      style={{
        background: 'linear-gradient(135deg, var(--color-spotlight-from), var(--color-spotlight-to))',
      }}
    >
      {/* Purely decorative — an ambient glow, not content, so it's hidden from AT. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-10 -top-16 size-56 rounded-full bg-white/10 sm:size-72"
      />

      <div className="relative z-10 min-w-0">
        <div className="text-xs font-semibold uppercase tracking-widest text-white/90">
          {checkedIn ? 'On the clock' : completedToday ? 'Today' : 'Ready when you are'}
        </div>

        {checkedIn && elapsed ? (
          <div
            className="mt-1.5 font-[family-name:var(--font-display)] text-4xl font-bold tabular-nums leading-none sm:text-5xl lg:text-6xl"
            aria-live="off"
          >
            {elapsed}
          </div>
        ) : (
          <div className="mt-1.5 font-[family-name:var(--font-display)] text-2xl font-semibold leading-tight sm:text-3xl">
            {completedToday ? 'Attendance completed' : "You haven't checked in yet"}
          </div>
        )}

        <p className="mt-2.5 text-sm text-white/85 sm:text-base">{subtext(today)}</p>
      </div>

      <Link
        to={checkedIn ? '/attendance/check-out' : '/attendance/check-in'}
        className="relative z-10 inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-lg bg-white px-7 text-sm font-semibold text-accent-700 shadow-lg shadow-black/20 transition-transform hover:scale-[1.02] active:scale-[0.98] sm:h-13 sm:text-base"
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
