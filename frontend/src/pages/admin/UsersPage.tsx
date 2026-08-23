/**
 * Employee management (§8, §10) — TENANT_ADMIN only (enforced server-side;
 * this page is only ever mounted behind that route guard). Search is
 * debounced and server-side (the backend's own `search` param — §10), so
 * this never fetches the whole tenant just to filter client-side, and never
 * issues a request per keystroke.
 */
import { useState } from 'react'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/Select'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { CreateEmployeeDialog } from '@/features/users/admin/CreateEmployeeDialog'
import { EmployeeTable } from '@/features/users/admin/EmployeeTable'
import { roleLabel } from '@/features/users/admin/roleLabels'
import { useUsersList } from '@/features/users/admin/useUsersList'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { ASSIGNABLE_ROLES } from '@/lib/api/types'
import type { UserRole, UserStatus } from '@/lib/api/types'

type RoleFilter = 'ALL' | UserRole
type StatusFilter = 'ALL' | UserStatus

export default function UsersPage() {
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<RoleFilter>('ALL')
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)
  const debouncedSearch = useDebouncedValue(search)

  const { data, isPending, isError, error, refetch, isFetching } = useUsersList({
    search: debouncedSearch || undefined,
    role: role === 'ALL' ? undefined : role,
    status: status === 'ALL' ? undefined : status,
    page,
  })

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Manage employees</h1>
          <p className="text-sm text-foreground-muted">Create, edit, and manage roles for people in your tenant.</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" aria-hidden="true" />
          Add employee
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          label="Search"
          placeholder="Search by name, email, or code"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
          className="sm:max-w-xs"
        />
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-foreground">Role</span>
          <Select
            value={role}
            onValueChange={(value) => {
              setRole(value as RoleFilter)
              setPage(1)
            }}
          >
            <SelectTrigger aria-label="Filter by role" className="sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All roles</SelectItem>
              {ASSIGNABLE_ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {roleLabel(r)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-foreground">Status</span>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value as StatusFilter)
              setPage(1)
            }}
          >
            <SelectTrigger aria-label="Filter by status" className="sm:w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All statuses</SelectItem>
              <SelectItem value="ACTIVE">Active</SelectItem>
              <SelectItem value="INACTIVE">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {isPending && (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={refetch} />}

      {data && (
        <>
          <EmployeeTable employees={data.items} />

          {data.pagination.total_pages > 1 && (
            <nav aria-label="Employee pages" className="flex items-center justify-between pt-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={data.pagination.page <= 1 || isFetching}
                onClick={() => setPage(data.pagination.page - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-foreground-muted">
                Page {data.pagination.page} of {data.pagination.total_pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={data.pagination.page >= data.pagination.total_pages || isFetching}
                onClick={() => setPage(data.pagination.page + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}

      <CreateEmployeeDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
