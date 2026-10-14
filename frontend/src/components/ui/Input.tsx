import { Eye, EyeOff } from 'lucide-react'
import { forwardRef, useId, useState } from 'react'

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
    // Every password field gets a show/hide toggle, so it lives here rather
    // than being re-implemented per form. Visibility is local, per-field state.
    const isPassword = props.type === 'password'
    const [revealed, setRevealed] = useState(false)
    // The icon shows the current state (open eye = visible, slashed eye = hidden);
    // the accessible name below describes the action instead.
    const ToggleIcon = revealed ? Eye : EyeOff

    return (
      <div className="flex flex-col gap-1.5">
        {label && <Label htmlFor={inputId}>{label}</Label>}
        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            className={cn(
              'min-h-11 w-full rounded-xl border border-border-strong bg-surface-raised px-3.5 text-sm text-foreground',
              'placeholder:text-foreground-muted',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
              'disabled:cursor-not-allowed disabled:opacity-50',
              error && 'border-danger-500 focus-visible:ring-danger-500',
              isPassword && 'pr-12',
              className,
            )}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={cn(errorId, hintId) || undefined}
            {...props}
            type={isPassword && revealed ? 'text' : props.type}
          />
          {isPassword && (
            <button
              type="button"
              onClick={() => setRevealed((v) => !v)}
              aria-label={revealed ? 'Hide password' : 'Show password'}
              aria-pressed={revealed}
              className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-xl text-foreground-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ToggleIcon className="size-4" aria-hidden="true" />
            </button>
          )}
        </div>
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
