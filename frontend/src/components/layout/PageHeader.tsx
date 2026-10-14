import { cn } from '@/lib/utils/cn'

interface PageHeaderProps {
  /** Small tracked-uppercase label above the title (a date, a section, a role). */
  eyebrow?: string
  title: string
  description?: React.ReactNode
  /** A primary action aligned to the right of the title (wraps below it on a phone). */
  actions?: React.ReactNode
  className?: string
}

/**
 * The one page heading every signed-in screen uses: eyebrow, display-face
 * title, optional description and action. Before this each page hand-rolled
 * its own `<h1>` at a slightly different size, which is what made the first
 * pass of the redesign look half-finished on the admin screens.
 */
export function PageHeader({ eyebrow, title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex flex-wrap items-end justify-between gap-4', className)}>
      <div className="flex min-w-0 flex-col gap-2">
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-foreground-muted">{eyebrow}</p>
        )}
        <h1 className="font-[family-name:var(--font-display)] text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl">
          {title}
        </h1>
        {description && <p className="text-base text-foreground-muted">{description}</p>}
      </div>
      {actions}
    </div>
  )
}
