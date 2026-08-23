/**
 * Role change (§14) — a plain controlled `Select` rather than a full form,
 * since there's exactly one field. The backend enforces every real rule
 * here (no self-promotion beyond what it allows, no last-admin lockout, no
 * SUPER_ADMIN); this dialog's job is only to show whatever it says clearly
 * (§15) via `describeError`, not to guess the rule itself.
 */
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/Dialog'
import { Label } from '@/components/ui/Label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { ROLE_LABEL } from '@/features/users/admin/roleLabels'
import { useChangeEmployeeRole } from '@/features/users/admin/useUserMutations'
import { ASSIGNABLE_ROLES } from '@/lib/api/types'
import type { UserDetailResponse, UserRole } from '@/lib/api/types'
import { describeError } from '@/lib/errors/describeError'
import { toast } from '@/stores/toastStore'

export interface ChangeRoleDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  employee: UserDetailResponse
}

export function ChangeRoleDialog({ open, onOpenChange, employee }: ChangeRoleDialogProps) {
  const changeRole = useChangeEmployeeRole()
  const [role, setRole] = useState<UserRole>(employee.role as UserRole)
  const [error, setError] = useState<string | null>(null)

  async function handleConfirm() {
    setError(null)
    try {
      await changeRole.mutateAsync({ userId: employee.id, payload: { role } })
      toast.success('Role updated', `${employee.name} is now ${ROLE_LABEL[role]}.`)
      onOpenChange(false)
    } catch (err) {
      setError(describeError(err).message)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (changeRole.isPending) return
        if (next) setRole(employee.role as UserRole)
        setError(null)
        onOpenChange(next)
      }}
    >
      <DialogContent onEscapeKeyDown={(e) => changeRole.isPending && e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Change role</DialogTitle>
          <DialogDescription>Choose a new role for {employee.name}.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="change-role-select">Role</Label>
          <Select value={role} onValueChange={(value) => setRole(value as UserRole)}>
            <SelectTrigger id="change-role-select" aria-label="Role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASSIGNABLE_ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {ROLE_LABEL[r]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {error && (
            <p role="alert" className="text-xs text-danger-600">
              {error}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} disabled={changeRole.isPending}>
            Cancel
          </Button>
          <Button type="button" isLoading={changeRole.isPending} onClick={handleConfirm} disabled={role === employee.role}>
            {changeRole.isPending ? 'Saving…' : 'Save role'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
