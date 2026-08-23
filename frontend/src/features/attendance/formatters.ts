/**
 * Display-only time/date formatting for attendance screens. Never used to
 * compute anything — the backend is authoritative for state and duration;
 * this just renders the ISO timestamps it already returns.
 */

const TIME_FORMAT: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }
const DATE_FORMAT: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }

/** "9:04 AM" in the viewer's local timezone — the backend timestamp is UTC
 * (`TIMESTAMPTZ`), so this is the one place it becomes wall-clock time. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, TIME_FORMAT)
}

/** "Today, 9:04 AM" when the timestamp falls on the viewer's local today,
 * otherwise "Mon, Jan 5, 9:04 AM" — matches the check-in success copy in
 * the phase brief exactly for the common case. */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const isToday =
    date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth() && date.getDate() === now.getDate()
  const day = isToday ? 'Today' : date.toLocaleDateString(undefined, DATE_FORMAT)
  return `${day}, ${formatTime(iso)}`
}

/** "Mon, Jan 5" for a plain `date` (YYYY-MM-DD, no time component) — used in
 * the history list, which is naturally UTC-day-bucketed already. */
export function formatDay(isoDate: string): string {
  // Appending a UTC midnight time avoids the browser parsing a bare
  // `YYYY-MM-DD` as local midnight, which can roll it back a day west of UTC.
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString(undefined, { ...DATE_FORMAT, timeZone: 'UTC' })
}
