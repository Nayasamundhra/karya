import { useState } from 'react'

import { Button, type ButtonProps } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/Dialog'

export interface ConfirmationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  confirmVariant?: ButtonProps['variant']
  /** May reject — the dialog stays open and shows nothing further itself;
   * the caller is expected to surface the error (e.g. via a toast) and this
   * component just stops showing "Confirming…" once the promise settles. */
  onConfirm: () => Promise<void> | void
}

/**
 * The one place a destructive or hard-to-reverse action asks "are you sure".
 * Deliberately does not render its own error state — callers already have
 * an error-handling story (a toast, a form error) and duplicating it here
 * would mean two different failure UIs for one action.
 */
export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmVariant = 'primary',
  onConfirm,
}: ConfirmationDialogProps) {
  const [isConfirming, setIsConfirming] = useState(false)

  async function handleConfirm() {
    setIsConfirming(true)
    try {
      await onConfirm()
      onOpenChange(false)
    } finally {
      setIsConfirming(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !isConfirming && onOpenChange(next)}>
      <DialogContent onEscapeKeyDown={(e) => isConfirming && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={isConfirming}>
            {cancelLabel}
          </Button>
          <Button variant={confirmVariant} onClick={handleConfirm} isLoading={isConfirming}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
