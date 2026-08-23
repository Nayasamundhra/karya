/**
 * The dedicated check-in/check-out flow (§3/§9). One component drives both
 * directions — the backend request/response shape, evidence collected, and
 * failure modes are identical for `CHECK_IN` and `CHECK_OUT`; only the copy
 * and which mutation fires differ.
 *
 * Stages, matching the phase brief: Ready → Scanning → GPS → Submitting →
 * Result. Each stage advances itself as soon as it has what it needs
 * (§3: "do not force the employee through unnecessary screens") — the only
 * stage that waits for a tap is Ready, so a fresh page load doesn't spring a
 * camera-permission prompt with no warning.
 */
import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, ArrowLeft, QrCode, WifiOff } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { AttendanceCompleteIcon } from '@/features/attendance/AttendanceStatusCard'
import { formatTimestamp } from '@/features/attendance/formatters'
import { resolveOutcome, type AttendanceOutcome } from '@/features/attendance/outcome'
import { parseQrPayload, type QrPayload } from '@/features/attendance/qrPayload'
import { useCheckIn, useCheckOut } from '@/features/attendance/useAttendanceActions'
import { GEOLOCATION_ERROR_MESSAGES, useGeolocation } from '@/hooks/useGeolocation'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import type { AttendanceActionRequest, AttendanceActionResponse } from '@/lib/api/types'

// §22: `jsQR` and the canvas-sampling scanner load only once a check-in/out
// is actually in progress, not on the attendance home screen.
const QrScanner = lazy(() => import('@/features/attendance/QrScanner').then((m) => ({ default: m.QrScanner })))

type Stage = 'ready' | 'scanning' | 'gps' | 'submitting' | 'result'

export interface CheckInOutFlowProps {
  eventType: 'CHECK_IN' | 'CHECK_OUT'
}

const COPY = {
  CHECK_IN: {
    heading: 'Check in',
    ready: 'Scan the office QR code to check in.',
    start: 'Start check-in',
    successTitle: 'Check-in successful',
    successBody: "You're checked in.",
  },
  CHECK_OUT: {
    heading: 'Check out',
    ready: 'Scan the office QR code to check out.',
    start: 'Start check-out',
    successTitle: 'Check-out successful',
    successBody: "You're checked out.",
  },
} as const

export function CheckInOutFlow({ eventType }: CheckInOutFlowProps) {
  const navigate = useNavigate()
  const isOnline = useOnlineStatus()
  const copy = COPY[eventType]

  const [stage, setStage] = useState<Stage>('ready')
  const [scanKey, setScanKey] = useState(0)
  const [scanError, setScanError] = useState<string | null>(null)
  const [qrPayload, setQrPayload] = useState<QrPayload | null>(null)
  const [outcome, setOutcome] = useState<AttendanceOutcome | null>(null)
  const [successResponse, setSuccessResponse] = useState<AttendanceActionResponse | null>(null)
  // Belt-and-suspenders against a double submission racing the `stage`
  // state update itself (§8) — the mutation's own `isPending` covers the
  // common case, this covers the instant before the first render commits.
  const submittingRef = useRef(false)
  // Which GPS fix (by its own timestamp) has already been submitted, so a
  // "Try again" that returns to the `gps` stage requests a *fresh* fix
  // instead of instantly resubmitting the same stale one still sitting in
  // `useGeolocation`'s state.
  const submittedFixRef = useRef<number | null>(null)

  const geolocation = useGeolocation()
  const checkIn = useCheckIn()
  const checkOut = useCheckOut()
  const mutation = eventType === 'CHECK_IN' ? checkIn : checkOut

  const goHome = useCallback(() => navigate('/attendance'), [navigate])

  const submit = useCallback(
    async (payload: QrPayload, coords: NonNullable<typeof geolocation.coordinates>) => {
      if (submittingRef.current) return
      submittingRef.current = true
      submittedFixRef.current = coords.timestamp
      setStage('submitting')
      const request: AttendanceActionRequest = {
        latitude: coords.latitude,
        longitude: coords.longitude,
        accuracy_meters: coords.accuracy,
        challenge_id: payload.challenge_id,
        nonce: payload.nonce,
      }
      try {
        const response = await mutation.mutateAsync(request)
        setSuccessResponse(response)
        setOutcome(resolveOutcome(response))
      } catch (error) {
        setOutcome(resolveOutcome(error))
      } finally {
        submittingRef.current = false
        setStage('result')
      }
    },
    [mutation],
  )

  // GPS stage: request a fix on entry, then submit the instant one arrives —
  // no extra tap once the QR is already in hand (§3).
  useEffect(() => {
    if (stage !== 'gps' || !qrPayload) return
    const coords = geolocation.coordinates
    const isFreshFix = coords !== null && coords.timestamp !== submittedFixRef.current
    if (isFreshFix) {
      void submit(qrPayload, coords)
      return
    }
    if (!geolocation.isLoading && !geolocation.error) geolocation.request()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, qrPayload, geolocation.coordinates, geolocation.isLoading, geolocation.error])

  // Never leave a location request running behind a screen the employee has
  // already left (§15 spirit — nothing here is about coordinates surviving
  // the component, only about not doing needless work after unmount).
  useEffect(() => {
    return () => {
      if (geolocation.isLoading) geolocation.cancel()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleDecode(text: string) {
    const result = parseQrPayload(text)
    if (!result.ok) {
      setScanError("That doesn't look like a valid Karya QR code. Please scan the office QR display.")
      setScanKey((k) => k + 1)
      return
    }
    setScanError(null)
    setQrPayload(result.payload)
    setStage('gps')
  }

  function retryScan() {
    setOutcome(null)
    setSuccessResponse(null)
    setQrPayload(null)
    setScanError(null)
    setScanKey((k) => k + 1)
    setStage('scanning')
  }

  function retryGps() {
    setOutcome(null)
    setSuccessResponse(null)
    setStage('gps')
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="Back to attendance" onClick={goHome}>
          <ArrowLeft className="size-5" aria-hidden="true" />
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{copy.heading}</h1>
      </div>

      {!isOnline && stage !== 'result' && (
        <Alert variant="warning" title="You're offline">
          <p className="flex items-center gap-2">
            <WifiOff className="size-4 shrink-0" aria-hidden="true" />
            Attendance requires a connection. Reconnect and try again.
          </p>
        </Alert>
      )}

      {/* One shared live region for the stage's status — screen readers hear
       * exactly what changed without the visible layout needing its own
       * dedicated announcement text (§18). */}
      <p aria-live="polite" className="sr-only">
        {stageAnnouncement(stage)}
      </p>

      {stage === 'ready' && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 p-8 text-center">
            <QrCode className="size-10 text-foreground-muted" aria-hidden="true" />
            <p className="text-sm text-foreground-muted">{copy.ready}</p>
            <Button size="lg" className="w-full" disabled={!isOnline} onClick={() => setStage('scanning')}>
              {copy.start}
            </Button>
          </CardContent>
        </Card>
      )}

      {stage === 'scanning' && (
        <Card>
          <CardContent className="flex flex-col gap-3 p-6">
            {scanError && (
              <Alert variant="danger" title="Invalid QR code">
                {scanError}
              </Alert>
            )}
            <Suspense fallback={<Spinner label="Loading scanner…" className="mx-auto" />}>
              <QrScanner key={scanKey} active onDecode={handleDecode} />
            </Suspense>
          </CardContent>
        </Card>
      )}

      {stage === 'gps' && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            {geolocation.error ? (
              <>
                <AlertTriangle className="size-8 text-warning-600" aria-hidden="true" />
                <p className="text-sm text-foreground">{GEOLOCATION_ERROR_MESSAGES[geolocation.error]}</p>
                <Button variant="secondary" onClick={() => geolocation.request()}>
                  Try again
                </Button>
              </>
            ) : (
              <>
                <Spinner className="size-6" />
                <p className="text-sm text-foreground-muted">Getting your location…</p>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {stage === 'submitting' && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <Spinner className="size-6" />
            <p className="text-sm text-foreground-muted">Verifying…</p>
          </CardContent>
        </Card>
      )}

      {stage === 'result' && outcome && (
        <ResultCard
          outcome={outcome}
          copy={copy}
          response={successResponse}
          onRetryScan={retryScan}
          onRetryGps={retryGps}
          onDone={goHome}
        />
      )}
    </div>
  )
}

function stageAnnouncement(stage: Stage): string {
  switch (stage) {
    case 'scanning':
      return 'Scanning for QR code'
    case 'gps':
      return 'Getting your location'
    case 'submitting':
      return 'Verifying attendance'
    case 'result':
      return 'Result ready'
    default:
      return ''
  }
}

function ResultCard({
  outcome,
  copy,
  response,
  onRetryScan,
  onRetryGps,
  onDone,
}: {
  outcome: AttendanceOutcome
  copy: (typeof COPY)[keyof typeof COPY]
  response: AttendanceActionResponse | null
  onRetryScan: () => void
  onRetryGps: () => void
  onDone: () => void
}) {
  if (outcome.status === 'success') {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
          <AttendanceCompleteIcon className="size-10 text-success-600" aria-hidden="true" />
          <div>
            <p className="text-lg font-semibold text-foreground">{copy.successTitle}</p>
            <p className="text-sm text-foreground-muted">{copy.successBody}</p>
            {response?.event_timestamp && (
              <p className="mt-1 text-sm font-medium text-foreground">{formatTimestamp(response.event_timestamp)}</p>
            )}
          </div>
          <Button size="lg" className="w-full" onClick={onDone}>
            Done
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
        <Alert variant="danger" title={outcome.title} className="w-full text-left">
          {outcome.message}
        </Alert>
        {outcome.retryTarget === 'scan' && (
          <Button size="lg" className="w-full" onClick={onRetryScan}>
            Scan again
          </Button>
        )}
        {outcome.retryTarget === 'gps' && (
          <Button size="lg" className="w-full" onClick={onRetryGps}>
            Try again
          </Button>
        )}
        <Button variant="secondary" className="w-full" onClick={onDone}>
          Back to attendance
        </Button>
      </CardContent>
    </Card>
  )
}
