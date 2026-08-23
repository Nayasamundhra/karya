import { Badge } from '@/components/ui/Badge'
import type { DayStatus } from '@/lib/api/types'

/** The backend's own `DayStatus` vocabulary (`NO_RECORD` / `CHECKED_IN` /
 * `COMPLETED`) rendered consistently everywhere a manager/admin view shows
 * an employee's day — never invented client-side (see CLAUDE.md). Status is
 * always paired with text inside `Badge`, so it is never communicated by
 * color alone (§18). */
export function employeeStatusLabel(status: DayStatus): string {
  switch (status) {
    case 'CHECKED_IN':
      return 'Checked in'
    case 'COMPLETED':
      return 'Completed'
    case 'NO_RECORD':
    default:
      return 'No record'
  }
}

export function EmployeeStatusBadge({ status }: { status: DayStatus }) {
  switch (status) {
    case 'CHECKED_IN':
      return <Badge variant="success">Checked in</Badge>
    case 'COMPLETED':
      return <Badge variant="neutral">Completed</Badge>
    case 'NO_RECORD':
    default:
      return <Badge variant="warning">No record</Badge>
  }
}
