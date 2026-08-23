/**
 * The tenant's employee roster (§8) — a `Table` on desktop, cards on mobile,
 * same responsive split as `TeamAttendanceTable`. Each row's actions (edit,
 * change role, activate/deactivate) open one of the dedicated dialogs; the
 * destructive one (deactivate) goes through `ConfirmationDialog` first
 * (§13). Every mutation result — success or the backend's own refusal
 * message (last-admin, self-change) — surfaces via `toast`/`describeError`,
 * never a client-invented rule (§15/§23).
 */
import { useState } from 'react'
import { MoreVertical } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu'
import { EmptyState } from '@/components/feedback/EmptyState'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { ChangeRoleDialog } from '@/features/users/admin/ChangeRoleDialog'
import { EditEmployeeDialog } from '@/features/users/admin/EditEmployeeDialog'
import { roleLabel } from '@/features/users/admin/roleLabels'
import { useActivateEmployee, useDeactivateEmployee } from '@/features/users/admin/useUserMutations'
import { describeError } from '@/lib/errors/describeError'
import type { UserDetailResponse } from '@/lib/api/types'
import { toast } from '@/stores/toastStore'

export function EmployeeTable({ employees }: { employees: UserDetailResponse[] }) {
  const [editTarget, setEditTarget] = useState<UserDetailResponse | null>(null)
  const [roleTarget, setRoleTarget] = useState<UserDetailResponse | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<UserDetailResponse | null>(null)
  const activateEmployee = useActivateEmployee()
  const deactivateEmployee = useDeactivateEmployee()

  async function handleActivate(employee: UserDetailResponse) {
    try {
      await activateEmployee.mutateAsync(employee.id)
      toast.success('Employee activated', `${employee.name} can sign in again.`)
    } catch (error) {
      toast.error('Could not activate employee', describeError(error).message)
    }
  }

  async function handleDeactivateConfirmed() {
    if (!deactivateTarget) return
    try {
      await deactivateEmployee.mutateAsync(deactivateTarget.id)
      toast.success('Employee deactivated')
    } catch (error) {
      toast.error('Could not deactivate employee', describeError(error).message)
    }
  }

  if (employees.length === 0) {
    return <EmptyState title="No employees yet" description="Add your first employee to get started." />
  }

  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Employee code</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {employees.map((employee) => (
              <TableRow key={employee.id}>
                <TableCell className="font-medium">{employee.name}</TableCell>
                <TableCell className="text-foreground-muted">{employee.employee_code}</TableCell>
                <TableCell>{roleLabel(employee.role)}</TableCell>
                <TableCell>
                  <StatusBadge status={employee.status} />
                </TableCell>
                <TableCell className="text-right">
                  <RowActions
                    employee={employee}
                    onEdit={() => setEditTarget(employee)}
                    onChangeRole={() => setRoleTarget(employee)}
                    onDeactivate={() => setDeactivateTarget(employee)}
                    onActivate={() => handleActivate(employee)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Mobile card list */}
      <ul className="flex flex-col gap-2 md:hidden">
        {employees.map((employee) => (
          <li key={employee.id}>
            <Card>
              <CardContent className="flex items-start justify-between gap-2 p-4">
                <div className="flex flex-col gap-1">
                  <p className="text-sm font-medium text-foreground">{employee.name}</p>
                  <p className="text-xs text-foreground-muted">
                    {employee.employee_code} · {roleLabel(employee.role)}
                  </p>
                  <StatusBadge status={employee.status} />
                </div>
                <RowActions
                  employee={employee}
                  onEdit={() => setEditTarget(employee)}
                  onChangeRole={() => setRoleTarget(employee)}
                  onDeactivate={() => setDeactivateTarget(employee)}
                  onActivate={() => handleActivate(employee)}
                />
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>

      {editTarget && (
        <EditEmployeeDialog open onOpenChange={(open) => !open && setEditTarget(null)} employee={editTarget} />
      )}
      {roleTarget && (
        <ChangeRoleDialog open onOpenChange={(open) => !open && setRoleTarget(null)} employee={roleTarget} />
      )}
      {deactivateTarget && (
        <ConfirmationDialog
          open
          onOpenChange={(open) => !open && setDeactivateTarget(null)}
          title="Deactivate employee?"
          description={`${deactivateTarget.name} will no longer be able to sign in or record attendance.`}
          confirmLabel="Deactivate"
          confirmVariant="destructive"
          onConfirm={handleDeactivateConfirmed}
        />
      )}
    </>
  )
}

function StatusBadge({ status }: { status: string }) {
  return status === 'ACTIVE' ? <Badge variant="success">Active</Badge> : <Badge variant="neutral">Inactive</Badge>
}

function RowActions({
  employee,
  onEdit,
  onChangeRole,
  onDeactivate,
  onActivate,
}: {
  employee: UserDetailResponse
  onEdit: () => void
  onChangeRole: () => void
  onDeactivate: () => void
  onActivate: () => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Actions for ${employee.name}`}>
          <MoreVertical className="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onEdit}>Edit</DropdownMenuItem>
        <DropdownMenuItem onSelect={onChangeRole}>Change role</DropdownMenuItem>
        {employee.status === 'ACTIVE' ? (
          <DropdownMenuItem destructive onSelect={onDeactivate}>
            Deactivate
          </DropdownMenuItem>
        ) : (
          <DropdownMenuItem onSelect={onActivate}>Activate</DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
