/**
 * The single source of truth for Karya's web app manifest — imported by
 * `vite.config.ts` (so the built `manifest.webmanifest` comes from here) and
 * by `tests/unit/pwaManifest.test.ts` (so "the manifest has the fields a PWA
 * needs" is a real, checked assertion rather than something only visible by
 * reading the built output by hand).
 */
import type { ManifestOptions } from 'vite-plugin-pwa'

export const pwaManifest: Partial<ManifestOptions> = {
  name: 'Karya',
  short_name: 'Karya',
  description: 'Multi-tenant employee attendance and presence verification.',
  theme_color: '#0f172a',
  background_color: '#ffffff',
  display: 'standalone',
  start_url: '/',
  scope: '/',
  icons: [
    { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
    { src: '/icons/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
  ],
}
