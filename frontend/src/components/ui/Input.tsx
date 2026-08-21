import { forwardRef, useId } from 'react'

import { Label } from '@/components/ui/Label'
import { cn } from '@/lib/utils/cn'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  /** Rendered below the field, and wired to the input via `aria-describedby`
   * so a screen reader announces it as part of the field, not as unrelated
   * page text. */
  error?: string
  hint?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, id, ...props }, ref) => {
    const generatedId = useId()
    const inputId = id ?? generatedId
    const errorId = error ? `${inputId}-error` : undefined
    const hintId = hint ? `${inputId}-hint` : undefined

    return (
      <div className="flex flex-col gap-1.5">
        {label && <Label htmlFor={inputId}>{label}</Label>}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'min-h-11 w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-foreground',
            'placeholder:text-foreground-muted',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
            'disabled:cursor-not-allowed disabled:opacity-50',
            error && 'border-danger-500 focus-visible:ring-danger-500',
            className,
          )}
          aria-invalid={Boolean(error) || undefined}
          aria-describedby={cn(errorId, hintId) || undefined}
          {...props}
        />
        {hint && !error && (
          <p id={hintId} className="text-xs text-foreground-muted">
            {hint}
          </p>
        )}
        {error && (
          <p id={errorId} role="alert" className="text-xs text-danger-600">
            {error}
          </p>
        )}
      </div>
    )
  },
)
Input.displayName = 'Input'
