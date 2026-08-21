import { describe, expect, it } from 'vitest'

import { NAV_ITEMS, navItemsForRole } from '@/config/navigation'

describe('navItemsForRole', () => {
  it('gives STAFF no access to team or admin navigation', () => {
    const ids = navItemsForRole('STAFF').map((item) => item.id)
    expect(ids).toEqual(['home', 'attendance', 'profile'])
  })

  it('gives MANAGER team navigation but not user management', () => {
    const ids = navItemsForRole('MANAGER').map((item) => item.id)
    expect(ids).toContain('team')
    expect(ids).not.toContain('admin-users')
  })

  it('gives TENANT_ADMIN every tenant-scoped item, but SUPER_ADMIN is never granted any item implicitly', () => {
    const adminIds = navItemsForRole('TENANT_ADMIN').map((item) => item.id)
    expect(adminIds).toEqual(['home', 'attendance', 'team', 'admin-users', 'profile'])

    // SUPER_ADMIN is a platform role Karya's tenant-scoped app never grants
    // anything to implicitly (mirrors the backend's require_roles design —
    // see backend README §8a). It should see nothing unless a future item
    // explicitly lists it.
    expect(navItemsForRole('SUPER_ADMIN')).toEqual([])
  })

  it('returns nothing for an undefined role rather than throwing', () => {
    expect(navItemsForRole(undefined)).toEqual([])
  })

  it('every declared item names at least one role — an item with no roles would be dead code', () => {
    for (const item of NAV_ITEMS) {
      expect(item.roles.length).toBeGreaterThan(0)
    }
  })
})
