import { Slot } from '@radix-ui/react-slot'
import { type VariantProps, cva } from 'class-variance-authority'
import { forwardRef } from 'react'

import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils/cn'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium ' +
    'transition-colors disabled:pointer-events-none disabled:opacity-50 ' +
    // 44px is the WCAG 2.2 AA (2.5.8) minimum target size — kept even at the
    // small size so a touch interface never gets a button smaller than that.
    'min-h-11',
  {
    variants: {
      variant: {
        primary: 'bg-accent-600 text-white hover:bg-accent-700 active:bg-accent-700',
        secondary:
          'bg-surface-sunken text-foreground border border-border hover:bg-surface-raised',
        outline: 'border border-border-strong bg-transparent text-foreground hover:bg-surface-sunken',
        ghost: 'bg-transparent text-foreground hover:bg-surface-sunken',
        destructive: 'bg-danger-600 text-white hover:bg-danger-700 active:bg-danger-700',
      },
      size: {
        sm: 'px-3 text-sm',
        md: 'px-4 text-sm',
        lg: 'px-6 text-base',
        icon: 'w-11 shrink-0 px-0',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  /** Shows a spinner and disables the button, without changing its size or losing its label. */
  isLoading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, isLoading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    // Radix's `Slot` (used when `asChild`) requires exactly one element
    // child — it clones its props onto that one child rather than wrapping
    // it, which is what lets `<Button asChild><Link .../></Button>` render
    // as a single `<a>` with no extra wrapping `<button>`. Adding a sibling
    // `{isLoading && <Spinner/>}` node unconditionally (even when it
    // evaluates to `false`) breaks that "exactly one child" contract, so it
    // is only ever added on the plain-`<button>` path.
    const content = asChild ? (
      children
    ) : (
      <>
        {isLoading && <Spinner className="text-current" />}
        {children}
      </>
    )
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        {...props}
      >
        {content}
      </Comp>
    )
  },
)
Button.displayName = 'Button'
