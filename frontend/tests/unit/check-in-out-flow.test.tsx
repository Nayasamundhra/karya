import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { CheckInOutFlow } from '@/features/attendance/CheckInOutFlow'
import { ApiError } from '@/lib/api/errors'
import * as attendanceApi from '@/lib/api/endpoints/attendance'
import { TestQueryProvider } from './helpers/testQueryClient'

const CHALLENGE_ID = '3fa85f64-5717-4562-b3fc-2c963f66afa6'
const QR_TEXT = JSON.stringify({ challenge_id: CHALLENGE_ID, nonce: 'office-display-nonce' })

vi.mock('@/lib/api/endpoints/attendance', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/endpoints/attendance')>()
  return { ...actual, checkIn: vi.fn(), checkOut: vi.fn() }
})

// Camera hardware is out of scope for this suite (§20 mocks it) — this
// double stands in for the real scanner exactly at its public contract:
// call `onDecode` with whatever text a code would have contained.
vi.mock('@/features/attendance/QrScanner', () => ({
  QrScanner: ({ active, onDecode }: { active: boolean; onDecode: (text: string) => void }) =>
    active ? (
      <>
        <button onClick={() => onDecode(QR_TEXT)}>Simulate scan</button>
        <button onClick={() => onDecode('not-a-karya-qr-code')}>Simulate invalid scan</button>
      </>
    ) : null,
}))

function mockGeolocationSuccess(coords: { latitude: number; longitude: number; accuracy: number }) {
  const getCurrentPosition = vi.fn((onSuccess: PositionCallback) => {
    onSuccess({ coords: coords as GeolocationCoordinates, timestamp: 1_700_000_000_000 } as GeolocationPosition)
  })
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition, clearWatch: vi.fn(), watchPosition: vi.fn() },
  })
}

function mockGeolocationError(code: number) {
  const getCurrentPosition = vi.fn((_onSuccess: PositionCallback, onError?: PositionErrorCallback | null) => {
    onError?.({ code, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError)
  })
  Object.defineProperty(globalThis.navigator, 'geolocation', {
    configurable: true,
    value: { getCurrentPosition, clearWatch: vi.fn(), watchPosition: vi.fn() },
  })
}

function renderFlow(eventType: 'CHECK_IN' | 'CHECK_OUT' = 'CHECK_IN') {
  return render(
    <TestQueryProvider>
      <MemoryRouter initialEntries={[eventType === 'CHECK_IN' ? '/attendance/check-in' : '/attendance/check-out']}>
        <CheckInOutFlow eventType={eventType} />
      </MemoryRouter>
    </TestQueryProvider>,
  )
}

async function startAndScan() {
  await userEvent.click(screen.getByRole('button', { name: /start check-in/i }))
  await userEvent.click(await screen.findByRole('button', { name: /simulate scan/i }))
}

describe('CheckInOutFlow', () => {
  afterEach(() => {
    vi.mocked(attendanceApi.checkIn).mockReset()
    vi.mocked(attendanceApi.checkOut).mockReset()
    // @ts-expect-error -- test-only teardown of a jsdom global defined above
    delete globalThis.navigator.geolocation
  })

  it('starts on the Ready stage and only opens the scanner once the employee taps the primary action', () => {
    renderFlow()
    expect(screen.getByRole('heading', { name: 'Check in' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /simulate scan/i })).not.toBeInTheDocument()
  })

  it('sends only the four evidence fields the backend accepts — never tenant_id or user_id', async () => {
    mockGeolocationSuccess({ latitude: 12.9716, longitude: 77.5946, accuracy: 8 })
    vi.mocked(attendanceApi.checkIn).mockResolvedValue({
      success: true,
      event_type: 'CHECK_IN',
      status: 'CHECKED_IN',
      attendance_event_id: 'evt-1',
      event_timestamp: '2026-08-22T09:04:00Z',
      presence: null,
      reason: null,
    })
    renderFlow()

    await startAndScan()

    expect(await screen.findByText('Check-in successful')).toBeInTheDocument()
    expect(attendanceApi.checkIn).toHaveBeenCalledTimes(1)
    expect(attendanceApi.checkIn).toHaveBeenCalledWith({
      latitude: 12.9716,
      longitude: 77.5946,
      accuracy_meters: 8,
      challenge_id: CHALLENGE_ID,
      nonce: 'office-display-nonce',
    })
    expect(screen.getByText("You're checked in.")).toBeInTheDocument()
  })

  it('shows the check-out success copy and calls the check-out endpoint for a check-out flow', async () => {
    mockGeolocationSuccess({ latitude: 1, longitude: 2, accuracy: 5 })
    vi.mocked(attendanceApi.checkOut).mockResolvedValue({
      success: true,
      event_type: 'CHECK_OUT',
      status: 'NOT_CHECKED_IN',
      attendance_event_id: 'evt-2',
      event_timestamp: '2026-08-22T17:30:00Z',
      presence: null,
      reason: null,
    })
    renderFlow('CHECK_OUT')

    await userEvent.click(screen.getByRole('button', { name: /start check-out/i }))
    await userEvent.click(await screen.findByRole('button', { name: /simulate scan/i }))

    expect(await screen.findByText('Check-out successful')).toBeInTheDocument()
    expect(attendanceApi.checkOut).toHaveBeenCalledTimes(1)
    expect(attendanceApi.checkIn).not.toHaveBeenCalled()
  })

  it('rejects a malformed QR before ever calling the backend, and lets the employee rescan without restarting', async () => {
    mockGeolocationSuccess({ latitude: 1, longitude: 2, accuracy: 5 })
    vi.mocked(attendanceApi.checkIn).mockResolvedValue({
      success: true,
      event_type: 'CHECK_IN',
      status: 'CHECKED_IN',
      attendance_event_id: 'evt-3',
      event_timestamp: '2026-08-22T09:00:00Z',
      presence: null,
      reason: null,
    })
    renderFlow()
    await userEvent.click(screen.getByRole('button', { name: /start check-in/i }))
    await userEvent.click(await screen.findByRole('button', { name: /simulate invalid scan/i }))

    expect(await screen.findByText(/doesn't look like a valid karya qr code/i)).toBeInTheDocument()
    expect(attendanceApi.checkIn).not.toHaveBeenCalled()

    // The scanner is still up (still on the Scanning stage) — a real QR
    // scan now succeeds without the employee backing out and starting over.
    await userEvent.click(await screen.findByRole('button', { name: /^simulate scan$/i }))
    expect(await screen.findByText('Check-in successful')).toBeInTheDocument()
  })

  it('maps a QR_EXPIRED refusal to its message and offers "Scan again", which reopens the scanner', async () => {
    mockGeolocationSuccess({ latitude: 1, longitude: 2, accuracy: 5 })
    vi.mocked(attendanceApi.checkIn).mockResolvedValue({
      success: false,
      event_type: 'CHECK_IN',
      status: 'NOT_CHECKED_IN',
      attendance_event_id: null,
      event_timestamp: null,
      presence: null,
      reason: 'QR_EXPIRED',
    })
    renderFlow()
    await startAndScan()

    expect(await screen.findByText(/this qr code has expired/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /scan again/i }))
    expect(await screen.findByRole('button', { name: /simulate scan/i })).toBeInTheDocument()
  })

  it('maps OUTSIDE_GEOFENCE to its message and offers "Try again" instead of a re-scan — the QR is still valid', async () => {
    mockGeolocationSuccess({ latitude: 1, longitude: 2, accuracy: 5 })
    vi.mocked(attendanceApi.checkIn).mockResolvedValue({
      success: false,
      event_type: 'CHECK_IN',
      status: 'NOT_CHECKED_IN',
      attendance_event_id: null,
      event_timestamp: null,
      presence: null,
      reason: 'OUTSIDE_GEOFENCE',
    })
    renderFlow()
    await startAndScan()

    expect(await screen.findByText(/you appear to be outside the office area/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /scan again/i })).not.toBeInTheDocument()
  })

  it('never claims success on a network failure, and lets the employee retry explicitly', async () => {
    mockGeolocationSuccess({ latitude: 1, longitude: 2, accuracy: 5 })
    vi.mocked(attendanceApi.checkIn).mockRejectedValue(new ApiError({ kind: 'network', message: 'offline' }))
    renderFlow()
    await startAndScan()

    expect(await screen.findByText("Couldn't connect to Karya")).toBeInTheDocument()
    expect(screen.getByText('Your attendance was not confirmed.')).toBeInTheDocument()
    expect(screen.queryByText('Check-in successful')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('surfaces a denied GPS permission with the shared geolocation copy, and lets the employee retry', async () => {
    mockGeolocationError(1) // PERMISSION_DENIED
    renderFlow()
    await userEvent.click(screen.getByRole('button', { name: /start check-in/i }))
    await userEvent.click(await screen.findByRole('button', { name: /simulate scan/i }))

    expect(await screen.findByText(/location access was denied/i)).toBeInTheDocument()
    expect(attendanceApi.checkIn).not.toHaveBeenCalled()
  })

  it('disables the primary action while offline instead of letting a doomed request start', () => {
    Object.defineProperty(globalThis.navigator, 'onLine', { value: false, configurable: true })
    renderFlow()
    expect(screen.getByRole('button', { name: /start check-in/i })).toBeDisabled()
    expect(screen.getByText(/you're offline/i)).toBeInTheDocument()
    Object.defineProperty(globalThis.navigator, 'onLine', { value: true, configurable: true })
  })
})
