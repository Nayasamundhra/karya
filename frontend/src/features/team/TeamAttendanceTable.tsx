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
import { Search } from 'lucide-react'
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

function AvatarChip({ name }: { name: string }) {
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-manager-50 text-xs font-semibold text-manager-700">
      {name.slice(0, 1).toUpperCase()}
    </span>
  )
}

type StatusFilter = 'ALL' | DayStatus

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'CHECKED_IN', label: 'Checked In' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'NO_RECORD', label: 'No Record' },
]

export function TeamAttendanceTable({ employees }: { employees: TeamAttendanceMember[] }) {
  const [filter, setFilter] = useState<StatusFilter>('ALL')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  const filtered = useMemo(() => {
    const byStatus = filter === 'ALL' ? employees : employees.filter((e) => e.status === filter)
    const trimmed = query.trim().toLowerCase()
    if (!trimmed) return byStatus
    return byStatus.filter(
      (e) => e.name.toLowerCase().includes(trimmed) || e.employee_code.toLowerCase().includes(trimmed),
    )
  }, [employees, filter, query])

  function openEmployee(userId: string) {
    navigate(`/team/${userId}`)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-foreground-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            aria-label="Search employees"
            placeholder="Search employees…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-h-11 w-full rounded-md border border-border-strong bg-surface py-2 pl-9 pr-3 text-sm text-foreground placeholder:text-foreground-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
          />
        </div>
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
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No employees match"
          description={query.trim() ? 'Try a different name or code.' : 'Try a different status filter.'}
        />
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
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-3">
                        <AvatarChip name={employee.name} />
                        <span>{employee.name}</span>
                      </div>
                    </TableCell>
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
                      <div className="flex items-center gap-3">
                        <AvatarChip name={employee.name} />
                        <div>
                          <p className="text-sm font-medium text-foreground">{employee.name}</p>
                          <p className="text-xs text-foreground-muted">{employee.employee_code}</p>
                        </div>
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
