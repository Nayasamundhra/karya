/**
 * The employee home screen (§2 of the redesign plan): check-in/out is the
 * page, not a link off of it. Replaces the old generic "what's next" card
 * for STAFF only — see `pages/HomePage.tsx`.
 */
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { CheckInHero } from '@/features/attendance/CheckInHero'
import { TodayTimeline } from '@/features/attendance/TodayTimeline'
import { WeekHoursCard, WeekStats } from '@/features/attendance/WeekOverview'
import { useTodayAttendance } from '@/features/attendance/useTodayAttendance'

const DATE_FORMAT: Intl.DateTimeFormatOptions = { weekday: 'long', month: 'long', day: 'numeric' }

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export function EmployeeHome({ name, tenantName }: { name: string; tenantName?: string }) {
  const { data: today, isPending, isError, error, refetch } = useTodayAttendance()
  const firstName = name.trim().split(/\s+/)[0] ?? name

  return (
    <div className="flex max-w-4xl flex-col gap-5">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-foreground sm:text-3xl">
          {greeting()}, {firstName}
        </h1>
        <p className="mt-1 text-sm text-foreground-muted">
          {new Date().toLocaleDateString(undefined, DATE_FORMAT)}
          {tenantName ? ` · ${tenantName}` : ''}
        </p>
      </div>

      {isPending && <Skeleton className="h-44 w-full rounded-2xl" />}
      {isError && <ErrorState error={error} onRetry={refetch} />}
      {today && <CheckInHero today={today} />}

      {today && (
        <>
          <WeekStats today={today} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TodayTimeline day={today.day} />
            <WeekHoursCard today={today} />
          </div>
        </>
      )}
    </div>
  )
}
