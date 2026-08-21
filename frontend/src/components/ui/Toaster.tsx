import * as ToastPrimitive from '@radix-ui/react-toast'
import { CheckCircle2, Info, X, XCircle } from 'lucide-react'

import { type ToastVariant, useToastStore } from '@/stores/toastStore'
import { cn } from '@/lib/utils/cn'

const ICONS: Record<ToastVariant, typeof Info> = {
  default: Info,
  success: CheckCircle2,
  danger: XCircle,
}

const VARIANT_CLASSES: Record<ToastVariant, string> = {
  default: 'border-border bg-surface-raised text-foreground',
  success: 'border-success-500/30 bg-success-50 text-success-700',
  danger: 'border-danger-500/30 bg-danger-50 text-danger-700',
}

/** Mounted once in `providers.tsx`. Radix's `Toast.Root` gives each toast
 * the correct `role="status"`/`aria-live` semantics for §20's "screen-reader
 * friendly status messages" — a hand-rolled div queue would have to
 * reimplement that by hand and easily miss it. */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts)
  const dismiss = useToastStore((state) => state.dismiss)

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {toasts.map((t) => {
        const Icon = ICONS[t.variant]
        return (
          <ToastPrimitive.Root
            key={t.id}
            duration={5000}
            onOpenChange={(open) => !open && dismiss(t.id)}
            className={cn(
              'flex items-start gap-3 rounded-md border p-4 shadow-md',
              VARIANT_CLASSES[t.variant],
            )}
          >
            <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <div className="flex flex-col gap-0.5">
              <ToastPrimitive.Title className="text-sm font-medium">{t.title}</ToastPrimitive.Title>
              {t.description && (
                <ToastPrimitive.Description className="text-sm opacity-90">
                  {t.description}
                </ToastPrimitive.Description>
              )}
            </div>
            <ToastPrimitive.Close aria-label="Dismiss" className="ml-auto shrink-0 rounded p-1 hover:bg-black/5">
              <X className="size-4" aria-hidden="true" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        )
      })}
      <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-4 outline-none sm:bottom-4 sm:right-4" />
    </ToastPrimitive.Provider>
  )
}
