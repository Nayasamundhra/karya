/**
 * Service worker registration, called once from `main.tsx`.
 *
 * `injectRegister: false` in `vite.config.ts` means Vite does not inject its
 * own registration script — this is the only place `serviceWorker.register`
 * is called, which is what makes the "controllerchange → reload once" logic
 * below safe to reason about (a second, competing registration call
 * elsewhere could otherwise double-fire it).
 */

let hasReloadedForUpdate = false

export function registerServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return
  // Vite's PWA plugin disables the worker under `devOptions.enabled: false`
  // for dev (see vite.config.ts) — registering here in dev would just 404.
  if (import.meta.env.DEV) return

  window.addEventListener('load', () => {
    void navigator.serviceWorker
      .register('/service-worker.js', { type: 'module' })
      .catch((error: unknown) => {
        // Not fatal — Karya works with no service worker at all, just
        // without offline-shell support and without "Add to Home Screen".
        console.error('Service worker registration failed', error)
      })
  })

  // A new worker calls `clients.claim()` on activate (see
  // src/service-worker.ts), which fires this event in every open tab. A full
  // reload is the simplest way to guarantee the tab is now served by the new
  // worker and the new precached assets, and is safe here because Karya has
  // no unsaved client-side state worth preserving across it (attendance
  // mutations are never queued locally — see docs/pwa.md §13).
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hasReloadedForUpdate) return
    hasReloadedForUpdate = true
    window.location.reload()
  })
}
