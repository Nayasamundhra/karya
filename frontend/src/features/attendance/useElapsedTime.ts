import { useEffect, useState } from 'react'

/** "04:12:37" elapsed since `since` (an ISO timestamp), ticking every second
 * while `since` is set. Purely presentational — the backend's own
 * `first_check_in` timestamp is the source of truth; this only formats how
 * long ago it was, the same way a stopwatch reads a fixed start time. */
export function useElapsedTime(since: string | null): string | null {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!since) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [since])

  if (!since) return null

  const totalSeconds = Math.max(0, Math.floor((now - new Date(since).getTime()) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}
