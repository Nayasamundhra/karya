import * as LabelPrimitive from '@radix-ui/react-label'
import { forwardRef } from 'react'

import { cn } from '@/lib/utils/cn'

export const Label = forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn('text-sm font-medium text-foreground', className)}
    {...props}
  />
))
Label.displayName = 'Label'
