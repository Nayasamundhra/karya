import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// A separate config from vite.config.ts on purpose: the app build needs the
// PWA plugin and Tailwind's PostCSS pipeline, neither of which a component
// test exercises, and pulling them into the test run would only slow it
// down and add failure modes unrelated to the code under test.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    css: false,
    // src/config/env.ts validates these eagerly on import (by design — see
    // its header comment), so the test process needs a value for them even
    // though no test ever makes a real network call to it.
    env: {
      VITE_API_BASE_URL: 'http://127.0.0.1:8000',
      VITE_APP_ENV: 'development',
    },
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/types/api.generated.ts', 'src/service-worker.ts', 'src/**/*.d.ts'],
    },
  },
})
