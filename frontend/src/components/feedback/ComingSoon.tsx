import type { LucideIcon } from 'lucide-react'

export interface ComingSoonProps {
  icon: LucideIcon
  title: string
  description: string
  phase: string
}

/** For a route that exists (so navigation and role-gating can be exercised
 * now) but whose real feature is a later, explicitly separate phase — see
 * CLAUDE.md. Deliberately not an `EmptyState` (nothing failed to load here;
 * there is nothing to load yet). */
export function ComingSoon({ icon: Icon, title, description, phase }: ComingSoonProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border p-12 text-center">
      <Icon className="size-8 text-foreground-muted" aria-hidden="true" />
      <h1 className="text-lg font-semibold text-foreground">{title}</h1>
      <p className="max-w-sm text-sm text-foreground-muted">{description}</p>
      <span className="rounded-full bg-surface-sunken px-3 py-1 text-xs font-medium text-foreground-muted">
        Coming in {phase}
      </span>
    </div>
  )
}
