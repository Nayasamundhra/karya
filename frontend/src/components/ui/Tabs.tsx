import * as TabsPrimitive from '@radix-ui/react-tabs'
import { forwardRef } from 'react'

import { cn } from '@/lib/utils/cn'

export const Tabs = TabsPrimitive.Root

export const TabsList = forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn('flex gap-1 border-b border-border', className)}
    {...props}
  />
))
TabsList.displayName = 'TabsList'

export const TabsTrigger = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      'min-h-11 border-b-2 border-transparent px-3 text-sm font-medium text-foreground-muted',
      'hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      'data-[state=active]:border-accent-600 data-[state=active]:text-foreground',
      className,
    )}
    {...props}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

export const TabsContent = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn('pt-4 focus-visible:outline-none', className)}
    {...props}
  />
))
TabsContent.displayName = 'TabsContent'
