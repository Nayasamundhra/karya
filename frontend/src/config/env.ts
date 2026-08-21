/**
 * Frontend environment configuration — validated at startup.
 *
 * Vite only exposes variables prefixed `VITE_` to client code (see
 * `.env.example`), and this is the one place they are read. Nothing else in
 * the app should touch `import.meta.env` directly, so there is exactly one
 * place to audit for "does this leak a secret" and exactly one place that
 * fails loudly if configuration is missing or malformed.
 *
 * Parsing eagerly (at module load, not lazily on first use) is deliberate:
 * a misconfigured deployment should fail to render anything rather than fail
 * confusingly the first time a component reaches for a URL that isn't there.
 */
import { z } from 'zod'

const envSchema = z.object({
  /** No trailing slash enforced here; `apiUrl()` in lib/api/client.ts joins paths safely either way. */
  VITE_API_BASE_URL: z.string().url({
    message: 'VITE_API_BASE_URL must be a full URL, e.g. http://127.0.0.1:8000',
  }),
  VITE_APP_ENV: z.enum(['development', 'staging', 'production']).default('development'),
})

function parseEnv() {
  const result = envSchema.safeParse(import.meta.env)
  if (!result.success) {
    // Thrown, not logged-and-continued: every screen in this app depends on
    // knowing where the API is, so there is no safe degraded mode to fall
    // back to. This throws during module evaluation, before React renders
    // anything, which is what turns a missing .env into an obvious build-time
    // or boot-time failure instead of a mysteriously blank app.
    const issues = result.error.issues
      .map((issue) => `  - ${issue.path.join('.')}: ${issue.message}`)
      .join('\n')
    throw new Error(
      `Invalid frontend environment configuration:\n${issues}\n\n` +
        'Copy .env.example to .env.local and fill in the required values.',
    )
  }
  return result.data
}

const parsed = parseEnv()

export const env = {
  apiBaseUrl: parsed.VITE_API_BASE_URL.replace(/\/+$/, ''),
  appEnv: parsed.VITE_APP_ENV,
  isProduction: parsed.VITE_APP_ENV === 'production',
} as const
