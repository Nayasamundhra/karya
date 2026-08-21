/// <reference lib="webworker" />
/**
 * Karya's service worker — hand-written (`injectManifest`, not
 * `generateSW`) because the caching rule that matters most is a negative
 * one: **never cache an API response**. See `docs/pwa.md` for the full
 * strategy this file implements and why `generateSW`'s declarative
 * `runtimeCaching` rules were not expressive enough for it.
 *
 * Three rules, in order of how much they matter:
 *
 * 1. Every request to the backend (`VITE_API_BASE_URL`, or any same-origin
 *    `/api/...`, `/health`, `/ready` path) is `NetworkOnly` — no cache read,
 *    no cache write, no fallback. Attendance status, presence verification,
 *    QR challenges and account status must always reflect the current
 *    request or fail honestly; a cached "you are checked in" is worse than
 *    no answer at all.
 * 2. The build's own static assets (JS/CSS/icons/manifest) are precached, so
 *    the app shell can load offline after a first successful visit.
 * 3. Navigation (HTML document) requests try the network first and fall
 *    back to the precached shell only when genuinely offline — an offline
 *    shell, never offline *data*. This is the one piece of `§13`'s "offline
 *    shell support for static UI only".
 */
import { precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkFirst, NetworkOnly } from 'workbox-strategies'

declare const self: ServiceWorkerGlobalScope

// Injected by vite-plugin-pwa's `injectManifest` build step — there is no
// first-party type for this magic constant, so an explicit, narrow cast is
// the pragmatic exception to "avoid any" (see src/config/env.ts).
precacheAndRoute(
  (self as unknown as { __WB_MANIFEST: Array<{ url: string; revision: string | null }> }).__WB_MANIFEST,
)

const apiOrigin = (() => {
  try {
    return new URL(import.meta.env.VITE_API_BASE_URL).origin
  } catch {
    return null
  }
})()

registerRoute(
  ({ url }) =>
    (apiOrigin !== null && url.origin === apiOrigin) ||
    url.pathname.startsWith('/api/') ||
    url.pathname === '/health' ||
    url.pathname === '/ready',
  new NetworkOnly(),
)

registerRoute(new NavigationRoute(new NetworkFirst({ cacheName: 'karya-shell' })))

// Take over immediately on update rather than waiting for every open tab to
// close — Karya ships no data migrations the old and new shell would
// disagree about, so there is nothing an old worker protects by lingering.
self.addEventListener('install', () => {
  void self.skipWaiting()
})
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})
