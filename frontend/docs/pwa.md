# PWA strategy

## What's configured

`vite-plugin-pwa` with the `injectManifest` strategy (not `generateSW`) — see
`vite.config.ts` and `src/service-worker.ts`. `injectManifest` was chosen
specifically because Karya's caching rule is a negative one that needed to be
written by hand: **never cache a backend response**, not even opportunistically.
`generateSW`'s declarative `runtimeCaching` rules describe *how* to cache a
route; they don't cleanly express *"under no circumstances, ever"* the way an
explicit `NetworkOnly` strategy registered first does.

## The three rules, in `src/service-worker.ts`

1. **Every backend request is `NetworkOnly`.** Matched by origin
   (`VITE_API_BASE_URL`) and by path (`/api/...`, `/health`, `/ready`) as a
   same-origin-proxy fallback. No cache read, no cache write, no offline
   fallback. Attendance status, presence verification results, QR
   challenges, and account status must always reflect the live request or
   fail honestly — a cached "you're checked in" from an hour ago is actively
   dangerous in an attendance system, not just stale.
2. **Static build assets are precached** (`precacheAndRoute`), so the app
   shell — JS, CSS, icons, the manifest — loads even with no network, after
   at least one successful visit.
3. **Navigation requests are `NetworkFirst`**, falling back to the precached
   shell only when genuinely offline. This is deliberately narrower than
   "offline mode" — it is what makes `npm run preview` still show *a* Karya
   shell with no network, not a browser error page. It is not offline data.

## Explicitly not implemented: offline attendance

Karya's attendance system is security- and trust-sensitive by design (see
`CLAUDE.md` and backend README §8b–§8c). This phase does not, and Phase 9
must not, queue a check-in/check-out while offline for later replay. If
there's no live connection, the correct behaviour is to say so
(`useOnlineStatus` + `OfflineBanner`, `src/hooks/useOnlineStatus.ts` /
`src/components/layout/OfflineBanner.tsx`) and refuse the action — never to
fake a success or store an action for a background sync that could let a
stale, unverifiable claim of presence reach the server minutes or hours
later.

## Manifest

Single source of truth: `src/config/pwaManifest.ts`, imported by both
`vite.config.ts` (so the built manifest comes from it) and
`tests/unit/pwaManifest.test.ts` (so its required fields are actually
checked, not just assumed from reading the config by eye).

Icons are currently **placeholders** — a flat brand-colour square with a
lighter inset mark, generated with zero image-library dependencies by
`scripts/generate-placeholder-icons.mjs` (a ~90-line hand-rolled PNG encoder
over Node's `zlib`, since neither ImageMagick nor Pillow were available in
this environment). **Replace `public/icons/*.png` with real designed assets
before a production launch.**

## Platform differences — Android vs iOS

PWA support is **not** the same across platforms, and pretending otherwise
produces a feature that quietly only works half the time:

| Capability | Android (Chrome) | iOS (Safari) |
| --- | --- | --- |
| Install prompt (`beforeinstallprompt`) | ✅ Supported — `useInstallPrompt()` works | ❌ **No such event exists.** The hook's `canPromptInstall` is always `false` on iOS. |
| Installing to home screen | Programmatic, via the prompt above | **Manual only**: Share sheet → "Add to Home Screen". No web API can trigger or detect this. |
| Standalone display (no browser chrome) | Driven by the manifest's `display: standalone` | Requires the `apple-mobile-web-app-capable` meta tag (present in `index.html`) **in addition to** the manifest — the manifest alone does nothing on iOS. |
| Service worker | Full support | Supported, but historically with tighter storage eviction under memory pressure — don't assume a precache survives indefinitely. |
| Push notifications | Supported | Supported only from iOS 16.4+, and only for an already-installed (home-screen) PWA — never for a plain Safari tab. Not used by Karya at all yet. |

Any future "Install Karya" UI must branch on this — `useInstallPrompt()`'s
`canPromptInstall` tells you whether the Android/Chromium flow is available;
when it's `false`, the UI should fall back to written Share-sheet
instructions instead of silently showing nothing, per this file's guidance
and `src/hooks/useInstallPrompt.ts`'s own header comment.

## Verifying this by hand

`npm run dev` disables the service worker on purpose (`devOptions.enabled:
false` in `vite.config.ts`) — a stale worker intercepting requests during
development is a classic source of "why isn't my change showing up"
confusion. To see the real PWA behaviour:

```bash
npm run build && npm run preview
```

Then, in Chrome DevTools → Application: check the manifest renders with
icons, the service worker is `activated and running`, and Network → Offline
still serves the app shell for `/` but a real `fetch` to the backend fails
honestly instead of returning a cached body.
