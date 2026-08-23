import { useEffect, useState } from 'react'

/** Delays reflecting a fast-changing value (e.g. a search input) so callers
 * — the admin employee search (§10) — don't issue a request on every
 * keystroke. `delayMs` defaults to a comfortable typing pause. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
