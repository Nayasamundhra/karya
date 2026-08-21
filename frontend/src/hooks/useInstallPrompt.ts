/**
 * Wraps the `beforeinstallprompt` event so a component can offer an
 * "Install Karya" button instead of relying on the browser's own UI.
 *
 * PLATFORM LIMITATION, stated here because it is easy to build a feature
 * that quietly only works on one platform otherwise: `beforeinstallprompt`
 * is a Chromium extension (Chrome, Edge, Samsung Internet, desktop Chrome)
 * with **no Safari/iOS equivalent**. iOS Safari supports installing a PWA
 * to the home screen only through the manual Share → "Add to Home Screen"
 * flow, which no web API can trigger or detect programmatically. A component
 * using this hook must still show iOS users instructions for that manual
 * flow — see `docs/pwa.md` for the full platform-support table — rather
 * than silently having no install affordance at all on iOS.
 */
import { useEffect, useState } from 'react'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function useInstallPrompt() {
  const [deferredEvent, setDeferredEvent] = useState<BeforeInstallPromptEvent | null>(null)
  const [isInstalled, setIsInstalled] = useState(false)

  useEffect(() => {
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault()
      setDeferredEvent(event as BeforeInstallPromptEvent)
    }
    const onInstalled = () => {
      setIsInstalled(true)
      setDeferredEvent(null)
    }
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  return {
    /** Only ever true on Chromium browsers that haven't installed the app yet — never iOS Safari. */
    canPromptInstall: deferredEvent !== null,
    isInstalled,
    promptInstall: async () => {
      if (!deferredEvent) return null
      await deferredEvent.prompt()
      const choice = await deferredEvent.userChoice
      setDeferredEvent(null)
      return choice.outcome
    },
  }
}
