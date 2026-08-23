/**
 * The actual QR decoding UI (§4). Deliberately a separate module from
 * `CheckInOutFlow`, which lazy-imports this one (`React.lazy`) — that's what
 * keeps `jsQR` and this component's canvas-sampling code out of the bundle
 * for every screen that isn't actively scanning (§22).
 *
 * Camera access itself is `useCameraStream` (Phase 8) unchanged — this
 * component only adds the decode loop on top of the `<video>` it already
 * manages. Decoding samples the live video frame onto an off-screen canvas
 * on a fixed interval (not every animation frame) — enough to feel instant
 * while walking up to a display, without pegging the CPU (§4/§22). The
 * interval is cleared the instant a code decodes, on unmount, and whenever
 * `active` goes false, so nothing keeps sampling — or keeps the camera
 * running — after this screen is done with it (§4/§14).
 */
import { useEffect, useRef, useState } from 'react'
import jsQR from 'jsqr'

import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { CAMERA_ERROR_MESSAGES, useCameraStream } from '@/hooks/useCameraStream'

const SCAN_INTERVAL_MS = 200

export interface QrScannerProps {
  /** Only runs the camera and decode loop while true — set false as soon as
   * a code is accepted, so nothing keeps scanning behind a later stage. */
  active: boolean
  onDecode: (text: string) => void
}

export function QrScanner({ active, onDecode }: QrScannerProps) {
  const { permission, isLoading, error, videoRef, start, stop } = useCameraStream()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Guards against a second `onDecode` firing from a scan already in flight
  // when the parent hasn't yet flipped `active` to false (§8).
  const decodedRef = useRef(false)
  const [started, setStarted] = useState(false)

  useEffect(() => {
    if (!active) return
    decodedRef.current = false
    void start().then(() => setStarted(true))
    return () => {
      stop()
      setStarted(false)
    }
    // `start`/`stop` are stable (useCallback with no deps) — re-running this
    // effect is driven only by `active` toggling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  useEffect(() => {
    if (!active || !started) return

    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return

    const interval = setInterval(() => {
      if (decodedRef.current) return
      if (video.readyState < video.HAVE_CURRENT_DATA || video.videoWidth === 0) return

      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const frame = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const result = jsQR(frame.data, frame.width, frame.height)
      if (result?.data) {
        decodedRef.current = true
        clearInterval(interval)
        stop()
        onDecode(result.data)
      }
    }, SCAN_INTERVAL_MS)

    return () => clearInterval(interval)
  }, [active, started, videoRef, stop, onDecode])

  if (!active) return null

  if (error) {
    return (
      <Alert variant="danger" title="Camera unavailable">
        <p>{CAMERA_ERROR_MESSAGES[error]}</p>
        <Button variant="secondary" size="sm" className="mt-2" onClick={() => void start()}>
          Try again
        </Button>
      </Alert>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative aspect-square w-full max-w-sm overflow-hidden rounded-lg bg-black">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a live camera preview, not prerecorded media */}
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          aria-label="Live camera preview for scanning the office QR code"
          className="size-full object-cover"
        />
        {(isLoading || (permission !== 'granted' && !error)) && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <Spinner label="Starting camera…" className="text-white" />
          </div>
        )}
        <div className="pointer-events-none absolute inset-8 rounded-lg border-2 border-white/70" aria-hidden="true" />
      </div>
      <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
      <p className="text-center text-sm text-foreground-muted">Point your camera at the office QR code</p>
      {/* Announced without visually duplicating the copy above. */}
      <p role="status" className="sr-only">
        {permission === 'granted' ? 'Scanning for QR code' : 'Waiting for camera'}
      </p>
    </div>
  )
}
