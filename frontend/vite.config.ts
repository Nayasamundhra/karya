import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

import { pwaManifest } from './src/config/pwaManifest.ts'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      // `injectManifest` (not `generateSW`) because Karya needs a hand-written
      // fetch strategy: API requests must stay network-only (attendance state,
      // presence, QR challenges are never served stale), while static build
      // assets are precached. `generateSW`'s declarative runtimeCaching rules
      // cannot express "never cache, no fallback" as cleanly as an explicit
      // service worker can. See src/service-worker.ts and docs/pwa.md.
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'service-worker.ts',
      injectRegister: false, // registered explicitly in src/lib/pwa/register.ts
      manifest: pwaManifest,
      injectManifest: {
        // Precache only the built static bundle — never API responses.
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
      },
      devOptions: {
        // The service worker is disabled in `npm run dev` on purpose: a stale
        // worker intercepting requests during development is a classic source
        // of "why isn't my change showing up" confusion. Verify PWA/SW behaviour
        // against `npm run build && npm run preview` instead.
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
  },
})
