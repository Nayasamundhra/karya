import { WifiOff } from 'lucide-react'

import { useOnlineStatus } from '@/hooks/useOnlineStatus'

/**
 * A persistent, unmissable banner — not a toast that can be dismissed and
 * forgotten — because "attendance requires a live connection" (§13) is a
 * fact the user needs for as long as it's true, not a one-off notice.
 */
export function OfflineBanner() {
  const isOnline = useOnlineStatus()
  if (isOnline) return null

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 bg-warning-500 px-4 py-2 text-sm font-medium text-white"
    >
      <WifiOff className="size-4" aria-hidden="true" />
      <span>You&apos;re offline. Attendance and other actions require a live connection.</span>
    </div>
  )
}
