/**
 * Two steps in one dialog: name the kiosk, then see its token exactly once.
 * The dialog cannot be dismissed by the usual means during that second step
 * without an explicit acknowledgement — there is no way to retrieve this
 * value again, only to revoke it and mint a replacement.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Check, Copy } from 'lucide-react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import {
  createDisplayTokenSchema,
  type CreateDisplayTokenFormValues,
} from '@/features/display/displayTokenSchema'
import { useCreateDisplayToken } from '@/features/display/useDisplayTokenMutations'
import { describeError } from '@/lib/errors/describeError'
import type { DisplayTokenCreateResponse } from '@/lib/api/types'

export interface CreateDisplayTokenDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateDisplayTokenDialog({ open, onOpenChange }: CreateDisplayTokenDialogProps) {
  const createDisplayToken = useCreateDisplayToken()
  const [created, setCreated] = useState<DisplayTokenCreateResponse | null>(null)
  const [copied, setCopied] = useState(false)
  const [submitError, setSubmitError] = useState<unknown>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateDisplayTokenFormValues>({
    resolver: zodResolver(createDisplayTokenSchema),
    defaultValues: { label: '' },
  })

  function close(next: boolean) {
    if (!next) {
      reset()
      setCreated(null)
      setCopied(false)
      setSubmitError(null)
    }
    onOpenChange(next)
  }

  async function onSubmit(values: CreateDisplayTokenFormValues) {
    setSubmitError(null)
    try {
      const result = await createDisplayToken.mutateAsync({ label: values.label })
      setCreated(result)
    } catch (error) {
      setSubmitError(error)
    }
  }

  async function copyToken() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
    } catch {
      // Clipboard access can be denied (permissions, insecure context); the
      // token is still selectable text in the field below either way.
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (createDisplayToken.isPending ? null : close(next))}>
      <DialogContent onEscapeKeyDown={(e) => createDisplayToken.isPending && e.preventDefault()}>
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle>{created.label} is ready</DialogTitle>
              <DialogDescription>
                Copy this token now — it won't be shown again. On the display device, open{' '}
                <code>/display</code>, paste it in, and leave the page open.
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-2">
              <Input readOnly value={created.token} className="font-mono text-xs" aria-label="Display token" />
              <Button type="button" variant="secondary" size="icon" onClick={() => void copyToken()} aria-label="Copy token">
                {copied ? <Check className="size-4" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
              </Button>
            </div>
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Set up a new display</DialogTitle>
              <DialogDescription>
                Name it after where it'll sit — e.g. "Reception tablet". You'll get a one-time setup
                token for that device next.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
              {submitError !== null && <Alert variant="danger">{describeError(submitError).message}</Alert>}
              <Input label="Display name" placeholder="Reception tablet" error={errors.label?.message} {...register('label')} />
              <DialogFooter>
                <Button type="button" variant="secondary" onClick={() => close(false)} disabled={createDisplayToken.isPending}>
                  Cancel
                </Button>
                <Button type="submit" isLoading={createDisplayToken.isPending}>
                  {createDisplayToken.isPending ? 'Creating…' : 'Create display'}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
