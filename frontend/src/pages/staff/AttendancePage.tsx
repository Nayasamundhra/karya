import { CalendarClock } from 'lucide-react'

import { ComingSoon } from '@/components/feedback/ComingSoon'

export default function AttendancePage() {
  return (
    <ComingSoon
      icon={CalendarClock}
      title="Attendance"
      description="Check-in, check-out, GPS + QR presence verification, and your attendance history will live here."
      phase="Phase 9"
    />
  )
}
