/**
 * The full-screen, unattended kiosk view — what actually sits on the office
 * entrance screen. No employee data of any kind reaches this component: the
 * only thing it ever receives is a QR challenge (`challenge_id` + `nonce`),
 * which identifies neither a person nor even which tenant to a viewer (see
 * `app/schemas/presence.py`'s `QRChallengeResponse` docstring on the
 * backend) — there is deliberately no org name or display label anywhere on
 * this screen, since the backend never tells a display either one.
 *
 * The one bold gradient "spotlight" surface this app allows itself outside
 * the employee check-in hero (`styles/index.css`'s `--color-spotlight-*`) —
 * ambient, full-bleed, meant to read clearly from across a room, not a
 * dashboard glanced at up close.
 */
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { WifiOff } from 'lucide-react'

import { useDisplayQrChallenge } from '@/features/display/useDisplayQrChallenge'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'
import { isApiError } from '@/lib/api/errors'

export interface KioskDisplayProps {
  displayToken: string
  /** Called once the current token is confirmed unauthorized (revoked, or
   * simply never valid) — a condition no amount of retrying recovers from,
   * unlike a network blip. `KioskPage` uses this to drop back to the setup
   * screen instead of retrying forever against a dead credential. */
  onInvalidToken: () => void
}

const CLOCK_FORMAT: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit', second: '2-digit' }
const DATE_FORMAT: Intl.DateTimeFormatOptions = { weekday: 'long', month: 'long', day: 'numeric' }

export function KioskDisplay({ displayToken, onInvalidToken }: KioskDisplayProps) {
  const isOnline = useOnlineStatus()
  const {
    data: challenge,
    dataUpdatedAt,
    isFetching,
    isError,
    error,
  } = useDisplayQrChallenge(displayToken)
  const isRevoked = isApiError(error) && error.kind === 'unauthorized'

  useEffect(() => {
    if (isRevoked) onInvalidToken()
  }, [isRevoked, onInvalidToken])
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const secondsUntilRefresh = useCountdown(challenge?.expires_in ?? null, dataUpdatedAt)
  const clock = useClock()
  // Guards against a slow-resolving `toDataURL` call from an earlier
  // challenge overwriting a newer one that finished first.
  const latestChallengeId = useRef<string | null>(null)

  useEffect(() => {
    if (!challenge) return
    latestChallengeId.current = challenge.challenge_id
    const payload = JSON.stringify({ challenge_id: challenge.challenge_id, nonce: challenge.nonce })
    // Dark modules matched to --color-spotlight-from (#4f46e5) rather than
    // pure black, so the code reads as part of this screen, not a stock
    // library default — still comfortably high-contrast against the white
    // quiet zone for a camera to decode at a distance.
    QRCode.toDataURL(payload, { width: 480, margin: 2, color: { dark: '#3730a3', light: '#ffffff' } })
      .then((dataUrl) => {
        if (latestChallengeId.current === challenge.challenge_id) setQrDataUrl(dataUrl)
      })
      .catch(() => {
        // Rendering failure (should not happen for a well-formed payload) —
        // leave whatever QR is already on screen rather than blanking it.
      })
  }, [challenge])

  // Connection status is a UX hint about whether *this* screen can currently
  // mint fresh codes — never a claim about whether Karya itself is up.
  const connectionOk = isOnline && !isError

  return (
    <div
      className="relative flex min-h-screen flex-col overflow-hidden p-6 text-white sm:p-10"
      style={{
        background:
          'radial-gradient(120% 140% at 15% 10%, color-mix(in srgb, var(--color-spotlight-from) 70%, white) 0%, var(--color-spotlight-from) 42%, var(--color-spotlight-to) 78%, color-mix(in srgb, var(--color-spotlight-to) 80%, black) 100%)',
      }}
    >
      {/* Purely decorative ambient glow — hidden from AT. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 -bottom-32 size-[420px] rounded-full bg-white/10 blur-2xl sm:size-[560px]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-24 -top-24 size-72 rounded-full bg-white/5"
      />

      <div className="relative z-10 flex items-center justify-between">
        <div className="flex size-10 items-center justify-center rounded-lg bg-white/15 text-base font-bold">K</div>
        <div className="text-right">
          <div
            className="font-[family-name:var(--font-display)] text-2xl font-semibold tabular-nums sm:text-4xl"
            style={{ textShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
          >
            {clock.toLocaleTimeString(undefined, CLOCK_FORMAT)}
          </div>
          <div className="mt-0.5 text-xs text-white/90 sm:text-sm" style={{ textShadow: '0 1px 3px rgba(0,0,0,0.25)' }}>
            {clock.toLocaleDateString(undefined, DATE_FORMAT)}
          </div>
        </div>
      </div>

      <div className="relative z-10 flex flex-1 flex-col items-center justify-center gap-6 py-8 text-center">
        <div className="relative flex items-center justify-center">
          <div
            aria-hidden="true"
            className="animate-kiosk-breathe absolute rounded-[28px] border-2 border-white/35"
            style={{ width: 'min(88vw, 340px)', height: 'min(88vw, 340px)' }}
          />
          <div
            className="flex items-center justify-center rounded-2xl bg-white p-5 shadow-2xl shadow-black/30"
            style={{ width: 'min(75vw, 280px)', height: 'min(75vw, 280px)' }}
          >
            {qrDataUrl ? (
              // `alt=""`: a screen-reader user cannot scan this regardless,
              // and the adjacent paragraph already states what it's for.
              <img src={qrDataUrl} alt="" className="size-full object-contain" />
            ) : (
              <div className="size-full animate-pulse rounded-lg bg-surface-sunken" aria-hidden="true" />
            )}
          </div>
        </div>

        <div>
          <p className="font-[family-name:var(--font-display)] text-xl font-semibold sm:text-2xl">Scan to check in</p>
          <p className="mt-1.5 max-w-xs text-sm text-white/85 sm:text-base">
            Open your camera and point it at the code.
          </p>
        </div>
      </div>

      <div
        className="relative z-10 flex items-center justify-center gap-2 text-xs text-white/70"
        role="status"
        aria-live="polite"
        style={{ textShadow: '0 1px 3px rgba(0,0,0,0.25)' }}
      >
        {connectionOk ? (
          <>
            <span className="size-2 rounded-full bg-success-500" aria-hidden="true" />
            <span>
              {isFetching
                ? 'Refreshing…'
                : secondsUntilRefresh !== null
                  ? `Refreshing in ${secondsUntilRefresh}s`
                  : 'Ready'}
            </span>
          </>
        ) : (
          <>
            <WifiOff className="size-3.5 text-warning-400" aria-hidden="true" />
            <span>{isOnline ? "Can't reach Karya — retrying…" : 'This device is offline'}</span>
          </>
        )}
      </div>
    </div>
  )
}

/** Ticking wall clock — purely presentational, one shared render for both
 * the time and the date so they never drift a tick apart. */
function useClock(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

/**
 * Cosmetic-only countdown to the *next scheduled fetch* (not the QR's own
 * expiry — `useDisplayQrChallenge` always refetches a few seconds early, see
 * its own comment), ticking once a second purely from the server-supplied
 * `expiresInSeconds` and the moment React Query recorded this data as
 * fetched. Never used to decide anything — an expired/late tick still shows
 * whatever code is on screen until the real refetch replaces it.
 */
function useCountdown(expiresInSeconds: number | null, fetchedAt: number): number | null {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (expiresInSeconds === null) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [expiresInSeconds])

  if (expiresInSeconds === null || !fetchedAt) return null
  const elapsedSeconds = Math.floor((now - fetchedAt) / 1000)
  return Math.max(0, expiresInSeconds - elapsedSeconds)
}
