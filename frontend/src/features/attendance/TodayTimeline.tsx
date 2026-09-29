/** Today's check-in/check-out pairs, exactly as the backend recorded them
 * (`AttendanceDayResponse.sessions`) — no re-deriving anything the backend
 * already computed. */
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatTime } from '@/features/attendance/formatters'
import type { AttendanceDayResponse } from '@/lib/api/types'

export function TodayTimeline({ day }: { day: AttendanceDayResponse }) {
  const sessions = day.sessions ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Today's timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {sessions.length === 0 ? (
          <p className="text-sm text-foreground-muted">Nothing recorded yet today.</p>
        ) : (
          <ol className="flex flex-col">
            {sessions.map((session, index) => (
              <li key={session.check_in_event_id ?? session.check_out_event_id ?? index} className="flex gap-3">
                <div className="flex flex-col items-center pt-0.5">
                  <span className="size-2.5 shrink-0 rounded-full bg-employee-500" />
                  {index < sessions.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
                </div>
                <div className={index < sessions.length - 1 ? 'pb-4' : ''}>
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-foreground">
                    <span>
                      {session.check_in ? formatTime(session.check_in) : 'Before today'}
                      {' – '}
                      {session.check_out ? formatTime(session.check_out) : 'still on the clock'}
                    </span>
                    {session.check_out_auto_closed && (
                      <Badge variant="warning">Auto-closed — checkout missed</Badge>
                    )}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
