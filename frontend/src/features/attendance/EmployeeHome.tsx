/**
 * The employee home screen (§2 of the redesign plan): check-in/out is the
 * page, not a link off of it. Replaces the old generic "what's next" card
 * for STAFF only — see `pages/HomePage.tsx`.
 */
import { PageHeader } from '@/components/layout/PageHeader'
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

export function EmployeeHome({ name }: { name: string }) {
  const { data: today, isPending, isError, error, refetch } = useTodayAttendance()
  const firstName = name.trim().split(/\s+/)[0] ?? name

  return (
    <div className="flex max-w-4xl flex-col gap-5">
      <PageHeader
        eyebrow={new Date().toLocaleDateString(undefined, DATE_FORMAT)}
        title={`${greeting()}, ${firstName}.`}
      />

      {isPending && <Skeleton className="h-44 w-full rounded-3xl" />}
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
