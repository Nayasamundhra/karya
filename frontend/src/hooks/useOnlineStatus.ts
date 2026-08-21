import { useEffect, useState } from 'react'

/**
 * `navigator.onLine` plus the events that keep it fresh. This is what Phase
 * 9's check-in screen is expected to use to show "You're offline. Attendance
 * requires a live connection." instead of letting a submission attempt fail
 * confusingly against a dead network — see §13. Karya never queues an
 * attendance action for later replay; there is deliberately no
 * infrastructure here for that.
 *
 * `navigator.onLine` is a heuristic (it can be `true` on a network with no
 * real route to the internet), which is why this is a UX hint, not a
 * security boundary — a request that actually goes out and fails still
 * fails through the normal `ApiError` → `describeError` path.
 */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))

  useEffect(() => {
    const goOnline = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
    }
  }, [])

  return isOnline
}
