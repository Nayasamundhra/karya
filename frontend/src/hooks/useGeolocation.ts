/**
 * Geolocation infrastructure for Phase 9. This hook collects evidence — a
 * coordinate, an accuracy radius, and whatever went wrong — and nothing
 * more. It does not know what a geofence is, does not compare its output to
 * any location, and does not decide whether a position is "good enough" for
 * attendance. The backend is the only party that ever renders a verdict on
 * GPS evidence (see `app/services/presence/gps.py`); this hook exists so
 * Phase 9 doesn't have to write `navigator.geolocation` handling from
 * scratch under deadline.
 */
import { useCallback, useRef, useState } from 'react'

export type GeolocationPermission = 'unknown' | 'granted' | 'denied' | 'unsupported'

export interface GeolocationCoordinates {
  latitude: number
  longitude: number
  /** Meters; the browser's own confidence radius, forwarded to the backend
   * verbatim as `accuracy_meters` — never interpreted here. */
  accuracy: number
  /** When the browser produced this fix, for staleness checks by the caller. */
  timestamp: number
}

export type GeolocationErrorReason =
  | 'permission_denied'
  | 'position_unavailable'
  | 'timeout'
  | 'unsupported'
  | 'cancelled'

export interface UseGeolocationResult {
  permission: GeolocationPermission
  isLoading: boolean
  coordinates: GeolocationCoordinates | null
  error: GeolocationErrorReason | null
  /** Ask the browser for one fresh fix. Safe to call repeatedly (e.g. a "Retry" button). */
  request: () => void
  /** Abandon an in-flight request — used when the user navigates away mid-request. */
  cancel: () => void
}

interface UseGeolocationOptions {
  enableHighAccuracy?: boolean
  timeoutMs?: number
  /** How old a cached OS-level fix may be before the browser must poll fresh hardware. */
  maximumAgeMs?: number
}

function reasonForError(err: GeolocationPositionError): GeolocationErrorReason {
  switch (err.code) {
    case err.PERMISSION_DENIED:
      return 'permission_denied'
    case err.POSITION_UNAVAILABLE:
      return 'position_unavailable'
    case err.TIMEOUT:
      return 'timeout'
    default:
      return 'position_unavailable'
  }
}

export function useGeolocation(options: UseGeolocationOptions = {}): UseGeolocationResult {
  const { enableHighAccuracy = true, timeoutMs = 15_000, maximumAgeMs = 0 } = options

  const [permission, setPermission] = useState<GeolocationPermission>('unknown')
  const [isLoading, setIsLoading] = useState(false)
  const [coordinates, setCoordinates] = useState<GeolocationCoordinates | null>(null)
  const [error, setError] = useState<GeolocationErrorReason | null>(null)
  const watchIdRef = useRef<number | null>(null)

  const cancel = useCallback(() => {
    if (watchIdRef.current !== null) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
    setIsLoading(false)
    setError((current) => current ?? 'cancelled')
  }, [])

  const request = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setPermission('unsupported')
      setError('unsupported')
      return
    }

    setIsLoading(true)
    setError(null)

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setIsLoading(false)
        setPermission('granted')
        setCoordinates({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          timestamp: position.timestamp,
        })
      },
      (err) => {
        setIsLoading(false)
        const reason = reasonForError(err)
        setError(reason)
        if (reason === 'permission_denied') setPermission('denied')
      },
      { enableHighAccuracy, timeout: timeoutMs, maximumAge: maximumAgeMs },
    )
  }, [enableHighAccuracy, timeoutMs, maximumAgeMs])

  return { permission, isLoading, coordinates, error, request, cancel }
}

/** User-facing copy for each failure reason — kept next to the hook so
 * Phase 9 doesn't have to invent its own wording for a case this module
 * already knows about. */
export const GEOLOCATION_ERROR_MESSAGES: Record<GeolocationErrorReason, string> = {
  permission_denied: 'Location access was denied. Enable it in your browser or device settings to check in.',
  position_unavailable: "Your device couldn't determine a location. Move to an area with a clearer signal and try again.",
  timeout: 'Getting your location took too long. Try again.',
  unsupported: "This browser doesn't support location services.",
  cancelled: 'Location request cancelled.',
}
