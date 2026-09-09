/**
 * The office-display route: `/display`. Fully public — no login, no app
 * shell, no nav (see `router.tsx`) — because the physical device sitting at
 * an entrance has no person signed into it. It authenticates itself with a
 * display token stored in *this browser's* `localStorage`
 * (`displayTokenStorage.ts`), set up once by pasting the one-time token an
 * admin generated from the Displays tab under `/admin/organization`.
 */
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { KioskDisplay } from '@/features/display/KioskDisplay'
import {
  clearDisplayToken,
  loadDisplayToken,
  saveDisplayToken,
} from '@/features/display/displayTokenStorage'
import { revokeSelf } from '@/lib/api/endpoints/display'

export default function KioskPage() {
  const [storedToken, setStoredToken] = useState(() => loadDisplayToken())
  const [draft, setDraft] = useState('')
  const [isResetting, setIsResetting] = useState(false)

  if (storedToken) {
    const reset = () => {
      setIsResetting(true)
      const token = storedToken
      // Best-effort: revoke the credential server-side so it can't be reused
      // if this device (or the raw string) is compromised, then clear the
      // local copy regardless of whether the network call succeeds — a
      // kiosk that's offline, or whose token was already revoked by an
      // admin, must still be resettable from right here.
      revokeSelf(token)
        .catch(() => {
          // Already revoked, or unreachable — either way, the device is
          // being reset. Nothing further to do with the failure.
        })
        .finally(() => {
          clearDisplayToken()
          setStoredToken(null)
          setIsResetting(false)
        })
    }

    return (
      <div className="relative">
        <KioskDisplay
          displayToken={storedToken}
          onInvalidToken={() => {
            clearDisplayToken()
            setStoredToken(null)
          }}
        />
        {/* Deliberately tiny and out of the way — this device is meant to
         * run unattended for months; the reset control exists for the rare
         * case a kiosk is being repurposed or its token was revoked. */}
        <button
          type="button"
          onClick={reset}
          disabled={isResetting}
          className="absolute bottom-2 right-2 text-xs text-white/40 hover:text-white/80 disabled:pointer-events-none disabled:opacity-50"
        >
          {isResetting ? 'Resetting…' : 'Reset this display'}
        </button>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-sunken p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Set up this display</CardTitle>
          <CardDescription>
            Paste the one-time token from Admin → Displays. This token is remembered on this device
            only — nothing else here needs a sign-in.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault()
              const trimmed = draft.trim()
              if (!trimmed) return
              saveDisplayToken(trimmed)
              setStoredToken(trimmed)
            }}
          >
            <Input
              label="Display token"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="font-mono text-xs"
              autoComplete="off"
            />
            <Button type="submit" disabled={draft.trim().length === 0}>
              Activate this display
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
