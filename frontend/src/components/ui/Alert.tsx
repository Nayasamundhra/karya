import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'
import { type VariantProps, cva } from 'class-variance-authority'

import { cn } from '@/lib/utils/cn'

const alertVariants = cva('flex gap-3 rounded-md border p-4 text-sm', {
  variants: {
    variant: {
      info: 'border-info-500/30 bg-info-50 text-info-600',
      success: 'border-success-500/30 bg-success-50 text-success-700',
      warning: 'border-warning-500/30 bg-warning-50 text-warning-700',
      danger: 'border-danger-500/30 bg-danger-50 text-danger-700',
    },
  },
  defaultVariants: { variant: 'info' },
})

const ICONS = { info: Info, success: CheckCircle2, warning: AlertTriangle, danger: XCircle } as const

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof alertVariants> {
  title?: string
}

/** `role="alert"` only for `danger`/`warning` — an assertive live-region
 * announcement is right for "this failed", wrong for routine confirmations,
 * which would otherwise interrupt whatever the screen reader was already
 * saying. */
export function Alert({ className, variant = 'info', title, children, ...props }: AlertProps) {
  const Icon = ICONS[variant ?? 'info']
  return (
    <div
      className={cn(alertVariants({ variant }), className)}
      role={variant === 'danger' || variant === 'warning' ? 'alert' : 'status'}
      {...props}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-0.5">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-sm/relaxed opacity-90">{children}</div>}
      </div>
    </div>
  )
}
