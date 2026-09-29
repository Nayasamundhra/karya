import { Card, CardContent } from '@/components/ui/Card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { EmptyState } from '@/components/feedback/EmptyState'
import { formatHours } from '@/features/attendance/formatters'
import type { TeamMemberHoursResponse } from '@/lib/api/types'

/** Per-employee hours breakdown backing the same `/team/hours` response as
 * `TeamHoursCards` — a `Table` on desktop, a card list on mobile, matching
 * `TeamAttendanceTable`'s own split for "genuinely tabular desktop data". */
export function TeamHoursTable({ employees }: { employees: TeamMemberHoursResponse[] }) {
  if (employees.length === 0) {
    return <EmptyState title="No employees" description="Nothing to show yet." />
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="hidden md:block">
        <Table aria-label="Hours worked by employee">
          <TableHeader>
            <TableRow>
              <TableHead>Employee</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Today</TableHead>
              <TableHead>This week</TableHead>
              <TableHead>This month</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {employees.map((employee) => (
              <TableRow key={employee.user_id}>
                <TableCell className="font-medium">{employee.name}</TableCell>
                <TableCell className="text-foreground-muted">{employee.employee_code}</TableCell>
                <TableCell>{formatHours(employee.today_hours)}</TableCell>
                <TableCell>{formatHours(employee.week_hours)}</TableCell>
                <TableCell>{formatHours(employee.month_hours)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="flex flex-col gap-2 md:hidden">
        {employees.map((employee) => (
          <li key={employee.user_id}>
            <Card>
              <CardContent className="flex flex-col gap-2 p-4">
                <div>
                  <p className="text-sm font-medium text-foreground">{employee.name}</p>
                  <p className="text-xs text-foreground-muted">{employee.employee_code}</p>
                </div>
                <p className="flex flex-wrap gap-3 text-xs text-foreground-muted">
                  <span>Today {formatHours(employee.today_hours)}</span>
                  <span>Week {formatHours(employee.week_hours)}</span>
                  <span>Month {formatHours(employee.month_hours)}</span>
                </p>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}
