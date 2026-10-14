/**
 * Permanent deletion of an employee or manager — the one irreversible action
 * in employee management, so it asks for more than the generic
 * `ConfirmationDialog`: the admin has to type the person's name before the
 * button enables. Deactivation is the reversible alternative and the dialog
 * says so.
 *
 * Only the backend decides whether the delete is allowed (not yourself, not an
 * administrator); this dialog just shows whatever refusal it returns inline
 * and stays open, same as `ChangeRoleDialog`. The menu hides the action for
 * those two cases purely as a courtesy — see `EmployeeTable`.
 */
import { useState } from 'react'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/Dialog'
import { Input } from '@/components/ui/Input'
import { useDeleteEmployee } from '@/features/users/admin/useUserMutations'
import type { UserDetailResponse } from '@/lib/api/types'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export interface DeleteEmployeeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employee: UserDetailResponse
}

/** Compared trimmed and case-insensitively: this guards against a misclick,
 * not a typo-hunt — the point is that the admin read the name. */
function matchesName(typed: string, name: string): boolean {
  return typed.trim().toLowerCase() === name.trim().toLowerCase()
}

export function DeleteEmployeeDialog({ open, onOpenChange, employee }: DeleteEmployeeDialogProps) {
  const deleteEmployee = useDeleteEmployee()
  const [typed, setTyped] = useState('')
  const [error, setError] = useState<string | null>(null)
  const canDelete = matchesName(typed, employee.name)

  async function handleDelete() {
    setError(null)
    try {
      await deleteEmployee.mutateAsync(employee.id)
      toast.success('Employee deleted', `${employee.name} and their attendance history were permanently removed.`)
      onOpenChange(false)
    } catch (err) {
      setError(describeError(err).message)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (deleteEmployee.isPending) return
        setTyped('')
        setError(null)
        onOpenChange(next)
      }}
    >
      <DialogContent onEscapeKeyDown={(e) => deleteEmployee.isPending && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Delete {employee.name} permanently?</DialogTitle>
          <DialogDescription>
            This removes {employee.name} and every attendance record they have. It cannot be undone. If you only want
            to stop them signing in, deactivate them instead — that keeps their history.
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-4"
          noValidate
          onSubmit={(event) => {
            event.preventDefault()
            if (canDelete && !deleteEmployee.isPending) void handleDelete()
          }}
        >
          {error && <Alert variant="danger">{error}</Alert>}
          <Input
            label={`Type "${employee.name}" to confirm`}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            autoComplete="off"
            autoFocus
          />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={deleteEmployee.isPending}>
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={!canDelete} isLoading={deleteEmployee.isPending}>
              Delete permanently
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
