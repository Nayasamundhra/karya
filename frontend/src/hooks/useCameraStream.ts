/**
 * Camera-permission and stream foundation for Phase 9's QR scanner.
 *
 * This hook gets a live camera `MediaStream` onto a `<video>` element and
 * reports permission/availability state. It deliberately does **not**
 * decode barcodes — choosing and integrating a QR-decoding library (e.g.
 * one built on the `BarcodeDetector` API where available, with a JS
 * fallback elsewhere) is Phase 9's job, once the actual scanning UI exists
 * to decide things like scan-region framing and torch/zoom controls. Wiring
 * a decoder in now, with no screen to use it, would be complexity with no
 * consumer.
 *
 * The security boundary is unaffected either way: whatever a decoder reads
 * out of a QR code is just a `challenge_id` + `nonce` pair handed to
 * `POST /api/v1/presence/verify`, which is the only party that decides if
 * it's valid. This hook, and Phase 9's decoder, only ever produce evidence.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export type CameraPermission = 'unknown' | 'granted' | 'denied' | 'unsupported'

export type CameraErrorReason =
  | 'permission_denied'
  | 'no_camera'
  | 'camera_in_use'
  | 'unsupported'
  | 'unknown'

export interface UseCameraStreamResult {
  permission: CameraPermission
  isLoading: boolean
  error: CameraErrorReason | null
  /** Attach this to a `<video autoPlay muted playsInline ref={videoRef} />`. */
  videoRef: React.RefObject<HTMLVideoElement | null>
  start: () => Promise<void>
  stop: () => void
}

function reasonForError(err: unknown): CameraErrorReason {
  if (!(err instanceof DOMException)) return 'unknown'
  switch (err.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'permission_denied'
    case 'NotFoundError':
      return 'no_camera'
    case 'NotReadableError':
      return 'camera_in_use'
    default:
      return 'unknown'
  }
}

export function useCameraStream(): UseCameraStreamResult {
  const [permission, setPermission] = useState<CameraPermission>('unknown')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<CameraErrorReason | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  // Bumped by every `start()`/`stop()` call. `getUserMedia` is asynchronous,
  // so React 19's StrictMode dev double-invoke (mount → cleanup → mount)
  // — and any other back-to-back `start()` call, e.g. a fast permission
  // retry — can leave two calls in flight at once. Without this guard, the
  // *first* (stale) call resolves after the second, reassigns
  // `video.srcObject` back to its own now-orphaned stream, and aborts the
  // second call's already-playing `<video>.play()` with `AbortError` —
  // which reported as a generic, unrecoverable-looking "camera could not be
  // started" instead of ever reaching `permission: 'granted'`.
  const callIdRef = useRef(0)

  const stop = useCallback(() => {
    callIdRef.current += 1 // any in-flight start() from here on is stale
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  const start = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setPermission('unsupported')
      setError('unsupported')
      return
    }

    const callId = (callIdRef.current += 1)
    setIsLoading(true)
    setError(null)
    try {
      // Rear camera preferred ("environment") — front camera would be
      // pointed at the scanning person, not the office's QR display.
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      })
      if (callId !== callIdRef.current) {
        // Superseded by a later start()/stop() while getUserMedia was
        // pending — release this stream immediately rather than resurrect
        // a camera nothing is using any more.
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      if (callId !== callIdRef.current) return
      setPermission('granted')
    } catch (err) {
      if (callId !== callIdRef.current) return
      const reason = reasonForError(err)
      setError(reason)
      if (reason === 'permission_denied') setPermission('denied')
    } finally {
      if (callId === callIdRef.current) setIsLoading(false)
    }
  }, [])

  // Release the camera on unmount unconditionally — a QR scanner left
  // running behind a navigated-away screen is both a battery drain and a
  // (mild) privacy surprise.
  useEffect(() => stop, [stop])

  return { permission, isLoading, error, videoRef, start, stop }
}

export const CAMERA_ERROR_MESSAGES: Record<CameraErrorReason, string> = {
  permission_denied: 'Camera access was denied. Enable it in your browser or device settings to scan a QR code.',
  no_camera: 'No camera was found on this device.',
  camera_in_use: 'The camera is already in use by another app.',
  unsupported: "This browser doesn't support camera access.",
  unknown: 'The camera could not be started.',
}
