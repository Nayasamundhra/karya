import { describe, expect, it } from 'vitest'

import { pwaManifest } from '@/config/pwaManifest'

describe('PWA manifest', () => {
  it('has the fields required for installability', () => {
    expect(pwaManifest.name).toBe('Karya')
    expect(pwaManifest.short_name).toBeTruthy()
    expect(pwaManifest.display).toBe('standalone')
    expect(pwaManifest.start_url).toBe('/')
    expect(pwaManifest.theme_color).toMatch(/^#[0-9a-f]{6}$/i)
    expect(pwaManifest.background_color).toMatch(/^#[0-9a-f]{6}$/i)
  })

  it('declares a 192px and a 512px icon, plus a maskable icon for Android adaptive icons', () => {
    const icons = pwaManifest.icons ?? []
    expect(icons.some((icon) => icon.sizes === '192x192')).toBe(true)
    expect(icons.some((icon) => icon.sizes === '512x512' && !icon.purpose)).toBe(true)
    expect(icons.some((icon) => icon.purpose === 'maskable')).toBe(true)
  })

  it('every declared icon file actually exists in public/', async () => {
    const fs = await import('node:fs/promises')
    const path = await import('node:path')
    for (const icon of pwaManifest.icons ?? []) {
      const filePath = path.join(process.cwd(), 'public', icon.src.replace(/^\//, ''))
      await expect(fs.access(filePath)).resolves.toBeUndefined()
    }
  })
})
