/**
 * Today's team roster (§4/§5) — a `Table` on desktop (this is exactly the
 * "genuinely tabular desktop data" that component's own header comment calls
 * out) and a card list on mobile, both driven by the same already-loaded
 * `employees` array. Filtering is a plain in-memory `Array.filter` over data
 * the dashboard already has — no extra request per §17/§26.
 *
 * Deliberately excludes email, role, GPS, verification metadata, and the
 * user id from what's rendered (§4) — a click on a row is the only place the
 * id is used, to navigate to the detail route.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { EmptyState } from '@/components/feedback/EmptyState'
import { EmployeeStatusBadge } from '@/features/team/EmployeeStatusBadge'
import { formatTime } from '@/features/attendance/formatters'
import { cn } from '@/lib/utils/cn'
import type { DayStatus, TeamAttendanceMember } from '@/lib/api/types'

type StatusFilter = 'ALL' | DayStatus

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'CHECKED_IN', label: 'Checked In' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'NO_RECORD', label: 'No Record' },
]

export function TeamAttendanceTable({ employees }: { employees: TeamAttendanceMember[] }) {
  const [filter, setFilter] = useState<StatusFilter>('ALL')
  const navigate = useNavigate()

  const filtered = useMemo(
    () => (filter === 'ALL' ? employees : employees.filter((e) => e.status === filter)),
    [employees, filter],
  )

  function openEmployee(userId: string) {
    navigate(`/team/${userId}`)
  }

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Filter by attendance status" className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <Button
            key={f.value}
            type="button"
            variant={filter === f.value ? 'primary' : 'secondary'}
            size="sm"
            aria-pressed={filter === f.value}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </Button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <EmptyState title="No employees match this filter" description="Try a different status filter." />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Employee</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Check-in</TableHead>
                  <TableHead>Check-out</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((employee) => (
                  <TableRow
                    key={employee.user_id}
                    tabIndex={0}
                    role="button"
                    aria-label={`View attendance for ${employee.name}`}
                    className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
                    onClick={() => openEmployee(employee.user_id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        openEmployee(employee.user_id)
                      }
                    }}
                  >
                    <TableCell className="font-medium">{employee.name}</TableCell>
                    <TableCell className="text-foreground-muted">{employee.employee_code}</TableCell>
                    <TableCell>
                      <EmployeeStatusBadge status={employee.status} />
                    </TableCell>
                    <TableCell>{employee.check_in ? formatTime(employee.check_in) : '—'}</TableCell>
                    <TableCell>{employee.check_out ? formatTime(employee.check_out) : '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Mobile card list */}
          <ul className="flex flex-col gap-2 md:hidden">
            {filtered.map((employee) => (
              <li key={employee.user_id}>
                <Card
                  role="button"
                  tabIndex={0}
                  aria-label={`View attendance for ${employee.name}`}
                  className={cn(
                    'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  )}
                  onClick={() => openEmployee(employee.user_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      openEmployee(employee.user_id)
                    }
                  }}
                >
                  <CardContent className="flex flex-col gap-2 p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-foreground">{employee.name}</p>
                        <p className="text-xs text-foreground-muted">{employee.employee_code}</p>
                      </div>
                      <EmployeeStatusBadge status={employee.status} />
                    </div>
                    <p className="text-xs text-foreground-muted">
                      In {employee.check_in ? formatTime(employee.check_in) : '—'} · Out{' '}
                      {employee.check_out ? formatTime(employee.check_out) : '—'}
                    </p>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
