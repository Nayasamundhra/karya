import { type VariantProps, cva } from 'class-variance-authority'

import { cn } from '@/lib/utils/cn'

/**
 * Status is always paired with text inside the badge — never a bare dot or
 * color swatch — so it does not rely on color alone (WCAG 1.4.1). See
 * `src/features/attendance` (Phase 9) for the attendance-status usage this
 * exists for.
 */
export const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
  {
    variants: {
      variant: {
        neutral: 'bg-surface-sunken text-foreground-muted border border-border',
        accent: 'bg-accent-50 text-accent-700',
        success: 'bg-success-50 text-success-700',
        warning: 'bg-warning-50 text-warning-700',
        danger: 'bg-danger-50 text-danger-700',
        info: 'bg-info-50 text-info-600',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
)

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
