/**
 * "This week"/"Today"/"Streak" and the 7-day hours chart — split into two
 * components (`WeekStats`, `WeekHoursCard`) so `HomePage` can lay the
 * timeline and the chart side by side without either one duplicating the
 * data fetch (`useAttendanceHistory` shares one cached request per
 * identical query key — see `queryKeys.ts`).
 *
 * Every number here is arithmetic on timestamps the backend already
 * returned (duration = a session's own check_out minus its own check_in),
 * never a presence or business verdict. There's deliberately no "of 40h
 * expected" or "on time/late" comparison anywhere — Karya has no
 * shift/schedule concept (out of scope, see CLAUDE.md), so a number
 * implying one would be fabricated, not derived.
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { useAttendanceHistory } from '@/features/attendance/useAttendanceHistory'
import type { AttendanceDayResponse, AttendanceSessionResponse, AttendanceTodayResponse } from '@/lib/api/types'

const DAY_MS = 24 * 60 * 60 * 1000
const DAY_LABEL = new Intl.DateTimeFormat(undefined, { weekday: 'short', timeZone: 'UTC' })

function utcDateString(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** Hours between two ISO timestamps, or 0 if either side is missing (an
 * open session in progress, or a session that crosses into another day). */
function sessionHours(session: AttendanceSessionResponse): number {
  if (!session.check_in || !session.check_out) return 0
  return (new Date(session.check_out).getTime() - new Date(session.check_in).getTime()) / (1000 * 60 * 60)
}

function dayHours(day: AttendanceDayResponse): number {
  return (day.sessions ?? []).reduce((total, session) => total + sessionHours(session), 0)
}

/** Same as `dayHours`, but counts a currently open session's hours-so-far
 * too (`now - its check_in`) rather than 0 — otherwise a stat tile would
 * read "0m" for someone the hero card next to it shows as hours into their
 * shift. Only meaningful for the live `AttendanceTodayResponse`, never for
 * a past day from history (which has nothing open to still be running). */
function dayHoursLive(today: AttendanceTodayResponse): number {
  const sessions = today.day.sessions ?? []
  const closed = sessions.reduce((total, session) => total + sessionHours(session), 0)
  if (today.state !== 'CHECKED_IN') return closed

  const openSession = [...sessions].reverse().find((session) => session.check_in && !session.check_out)
  const openStart = openSession?.check_in ?? today.day.first_check_in
  if (!openStart) return closed

  const liveHours = (Date.now() - new Date(openStart).getTime()) / (1000 * 60 * 60)
  return closed + Math.max(0, liveHours)
}

function formatHours(hours: number): string {
  const wholeMinutes = Math.round(hours * 60)
  const h = Math.floor(wholeMinutes / 60)
  const m = wholeMinutes % 60
  if (h === 0) return `${m}m`
  return m === 0 ? `${h}h` : `${h}h ${m}m`
}

/** Consecutive days with a real attendance record, most recent first,
 * stopping at the first gap — a plain count over already-returned days. */
function streak(daysNewestFirst: AttendanceDayResponse[]): number {
  let count = 0
  for (const day of daysNewestFirst) {
    if (day.status === 'NO_RECORD') break
    count += 1
  }
  return count
}

function useLastSevenDays() {
  const today = new Date()
  const toDate = utcDateString(today)
  const fromDate = utcDateString(new Date(today.getTime() - 6 * DAY_MS))
  return useAttendanceHistory({ fromDate, toDate, pageSize: 7 })
}

export function WeekStats({ today }: { today?: AttendanceTodayResponse }) {
  const { data, isPending, isError } = useLastSevenDays()

  if (isPending) {
    return (
      <div className="grid grid-cols-3 gap-2 sm:gap-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }
  // Supplementary data — a failed fetch here just doesn't render rather
  // than crowding the page with a second error banner under the hero's own.
  if (isError || !data) return null

  const daysNewestFirst = data.items
  const todaySummary = daysNewestFirst[0]
  const todayIso = utcDateString(new Date())
  // Swap in the live-inclusive figure for whichever history row is today's,
  // so "This week" and "Today" agree with what the hero card is showing.
  const todayHours = today ? dayHoursLive(today) : todaySummary ? dayHours(todaySummary) : 0
  const totalHours = daysNewestFirst.reduce(
    (sum, day) => sum + (day.date === todayIso ? todayHours : dayHours(day)),
    0,
  )
  const streakDays = streak(daysNewestFirst)

  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-4">
      <StatTile label="This week" value={formatHours(totalHours)} />
      <StatTile label="Today" value={formatHours(todayHours)} />
      <StatTile label="Streak" value={streakDays === 1 ? '1 day' : `${streakDays} days`} />
    </div>
  )
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="min-w-0">
      <CardContent className="flex flex-col gap-1 p-3 sm:p-5">
        <span className="truncate text-[11px] font-semibold uppercase tracking-wide text-foreground-muted sm:text-xs">
          {label}
        </span>
        <span className="truncate font-[family-name:var(--font-display)] text-lg font-semibold text-employee-700 sm:text-2xl">
          {value}
        </span>
      </CardContent>
    </Card>
  )
}

export function WeekHoursCard({ today }: { today?: AttendanceTodayResponse }) {
  const { data, isPending, isError } = useLastSevenDays()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Last 7 days</CardTitle>
      </CardHeader>
      <CardContent>
        {isPending && <Skeleton className="h-28 w-full" />}
        {(isError || !data) && !isPending ? (
          <p className="text-sm text-foreground-muted">Couldn't load this week's hours.</p>
        ) : null}
        {data && <WeekChart daysNewestFirst={data.items} today={today} />}
      </CardContent>
    </Card>
  )
}

function WeekChart({
  daysNewestFirst,
  today,
}: {
  daysNewestFirst: AttendanceDayResponse[]
  today?: AttendanceTodayResponse
}) {
  const days = [...daysNewestFirst].reverse() // oldest first, so the chart reads left-to-right
  const todayIso = utcDateString(new Date())
  const hours = days.map((day) => (today && day.date === todayIso ? dayHoursLive(today) : dayHours(day)))
  const max = Math.max(1, ...hours)

  return (
    <div className="flex h-28 items-end gap-2 sm:gap-3">
      {days.map((day, index) => {
        const isToday = day.date === todayIso
        const value = hours[index] ?? 0
        const heightPercent = value === 0 ? 0 : Math.max(6, (value / max) * 100)
        return (
          <div key={day.date} className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
            <div className="flex h-20 w-full items-end">
              <div
                className={isToday ? 'w-full rounded-sm bg-employee-500' : 'w-full rounded-sm bg-border-strong'}
                style={{ height: `${heightPercent}%` }}
                title={`${DAY_LABEL.format(new Date(`${day.date}T00:00:00Z`))}: ${formatHours(value)}`}
              />
            </div>
            <span
              className={isToday ? 'text-[11px] font-semibold text-employee-700' : 'text-[11px] text-foreground-muted'}
            >
              {DAY_LABEL.format(new Date(`${day.date}T00:00:00Z`))}
            </span>
          </div>
        )
      })}
    </div>
  )
}
