import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useGeolocation } from '@/hooks/useGeolocation'

function mockGeolocation(
  implementation: (
    onSuccess: PositionCallback,
    onError?: PositionErrorCallback | null,
  ) => void,
) {
  const getCurrentPosition = vi.fn(implementation)
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition, clearWatch: vi.fn(), watchPosition: vi.fn() },
  })
  return getCurrentPosition
}

describe('useGeolocation', () => {
  afterEach(() => {
    // @ts-expect-error -- test-only teardown of a jsdom global we defined above
    delete globalThis.navigator.geolocation
    vi.restoreAllMocks()
  })

  it('reports coordinates and accuracy on success, and forwards them unmodified', async () => {
    mockGeolocation((onSuccess) => {
      onSuccess({
        coords: { latitude: 12.9716, longitude: 77.5946, accuracy: 8.2 } as GeolocationCoordinates,
        timestamp: 1_700_000_000_000,
      } as GeolocationPosition)
    })

    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())

    await waitFor(() => expect(result.current.coordinates).not.toBeNull())
    expect(result.current.permission).toBe('granted')
    expect(result.current.error).toBeNull()
    expect(result.current.coordinates).toEqual({
      latitude: 12.9716,
      longitude: 77.5946,
      accuracy: 8.2,
      timestamp: 1_700_000_000_000,
    })
  })

  it('maps PERMISSION_DENIED to a denied permission state, not a generic error', async () => {
    mockGeolocation((_onSuccess, onError) => {
      onError?.({ code: 1, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError)
    })

    const { result } = renderHook(() => useGeolocation())
    act(() => result.current.request())

    await waitFor(() => expect(result.current.error).toBe('permission_denied'))
    expect(result.current.permission).toBe('denied')
    expect(result.current.coordinates).toBeNull()
  })

  it('reports "unsupported" rather than throwing when the browser has no geolocation API', () => {
    // @ts-expect-error -- simulating an unsupported browser
    delete globalThis.navigator.geolocation
    const { result } = renderHook(() => useGeolocation())

    act(() => result.current.request())

    expect(result.current.permission).toBe('unsupported')
    expect(result.current.error).toBe('unsupported')
  })

  it('never decides geofence membership itself — it only ever exposes raw evidence', () => {
    const { result } = renderHook(() => useGeolocation())
    expect(result.current).not.toHaveProperty('isInsideGeofence')
    expect(result.current).not.toHaveProperty('verified')
  })
})
