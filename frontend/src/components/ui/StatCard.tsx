import { Card, CardContent } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils/cn'

/**
 * The one "headline number in a card" primitive — previously written three
 * times (`TeamHeadline`'s summary cards, `TeamSummaryCards`/`TeamHoursCards`,
 * `WeekOverview`'s local `StatTile`) with three slightly different visual
 * treatments.
 *
 * Shape (the brand redesign): a tracked-uppercase section label on top, the
 * number beneath it in the display face and the signed-in role's hue.
 * Tracked-uppercase labels are the brand's own signature (public pages use
 * the same style), so they are deliberate here, not a template tell.
 */
export type StatCardHue = 'employee' | 'manager' | 'admin'

const HUE_TEXT_CLASS: Record<StatCardHue, string> = {
  employee: 'text-employee-700',
  manager: 'text-manager-700',
  admin: 'text-admin-700',
}

export interface StatCardProps {
  label: string
  value: string
  hue?: StatCardHue
  className?: string
}

export function StatCard({ label, value, hue, className }: StatCardProps) {
  return (
    <Card className={cn('min-w-0', className)}>
      <CardContent className="flex flex-col gap-2 p-3 sm:p-6">
        {/* The label leads, in the brand's tracked-uppercase section-label
            style; the number beneath it is the thing the eye lands on. */}
        <span className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-foreground-muted sm:text-[11px] sm:tracking-[0.2em]">
          {label}
        </span>
        <span
          className={cn(
            'whitespace-nowrap font-[family-name:var(--font-display)] text-xl font-semibold leading-none tracking-tight sm:text-4xl',
            hue ? HUE_TEXT_CLASS[hue] : 'text-foreground',
          )}
        >
          {value}
        </span>
      </CardContent>
    </Card>
  )
}

export interface StatCardGridProps {
  ariaLabel: string
  columns?: 2 | 3 | 4
  className?: string
  children: React.ReactNode
}

/** Below `sm`: a 3-card grid stays three-across (the card's number and label
 * shrink to fit — a stack of three tall cards pushed the real content below
 * the fold on a phone), a 2- or 4-card grid halves to two columns. */
const GRID_COLS: Record<NonNullable<StatCardGridProps['columns']>, string> = {
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-2 sm:grid-cols-4',
}

export function StatCardGrid({ ariaLabel, columns = 4, className, children }: StatCardGridProps) {
  return (
    <div role="group" aria-label={ariaLabel} className={cn('grid gap-3', GRID_COLS[columns], className)}>
      {children}
    </div>
  )
}

export function StatCardSkeleton() {
  return (
    <Card className="min-w-0">
      <CardContent className="flex flex-col gap-3 p-5 sm:p-6">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-9 w-16" />
      </CardContent>
    </Card>
  )
}

export function StatCardGridSkeleton({ count = 4, columns = 4 }: { count?: number; columns?: 2 | 3 | 4 }) {
  return (
    <div className={cn('grid gap-3', GRID_COLS[columns])}>
      {Array.from({ length: count }, (_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  )
}
