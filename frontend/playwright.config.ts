import { defineConfig, devices } from '@playwright/test'

/**
 * §31's foundation: Chromium, one mobile viewport, one desktop viewport, and
 * a smoke test that needs no real GPS/camera hardware — the suite mocks the
 * backend at the network layer (`page.route`) rather than requiring a live
 * PostgreSQL-backed API in CI. See `tests/e2e/smoke.spec.ts` and
 * `docs/testing.md` for why, and for how a real end-to-end run against the
 * live backend (via the `backend:verify` skill's approach) is a separate,
 * deliberately not-automated-here concern.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: 'Desktop Chrome', use: { ...devices['Desktop Chrome'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 7'] } },
  ],
})
