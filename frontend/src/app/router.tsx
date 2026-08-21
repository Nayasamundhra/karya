import type { ComponentType } from 'react'
import type { RouteObject } from 'react-router-dom'
import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from '@/routes/guards'

/**
 * Route-level code splitting (§21): every page is a separate chunk, loaded
 * only when its route is actually visited. A STAFF user's bundle never
 * pulls in `pages/admin/*` — there is no `import` anywhere in their render
 * path that reaches it. `lazy()` here is React Router's own data-router
 * field (not `React.lazy`) — it wants a module exporting `Component`, so
 * this adapts our pages' plain `export default` to that shape in one place.
 */
function lazyRoute(importer: () => Promise<{ default: ComponentType }>) {
  return async () => {
    const { default: Component } = await importer()
    return { Component }
  }
}

/**
 * The route tree, exported separately from the browser router instance
 * below so tests can feed it to `createMemoryRouter` with an arbitrary
 * starting path instead of fighting `window.history` — see
 * `tests/unit/routing.test.tsx`.
 */
export const routes: RouteObject[] = [
  {
    path: '/login',
    lazy: async () => {
      const { default: LoginPage } = await import('@/pages/auth/LoginPage')
      return {
        Component: () => (
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        ),
      }
    },
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, lazy: lazyRoute(() => import('@/pages/HomePage')) },
          { path: 'attendance', lazy: lazyRoute(() => import('@/pages/staff/AttendancePage')) },
          { path: 'profile', lazy: lazyRoute(() => import('@/pages/ProfilePage')) },
          {
            element: <RequireRole roles={['MANAGER', 'TENANT_ADMIN']} />,
            children: [{ path: 'team', lazy: lazyRoute(() => import('@/pages/manager/TeamPage')) }],
          },
          {
            element: <RequireRole roles={['TENANT_ADMIN']} />,
            children: [{ path: 'admin/users', lazy: lazyRoute(() => import('@/pages/admin/UsersPage')) }],
          },
          { path: 'forbidden', lazy: lazyRoute(() => import('@/pages/ForbiddenPage')) },
        ],
      },
    ],
  },
  { path: '*', lazy: lazyRoute(() => import('@/pages/NotFoundPage')) },
]

export const router = createBrowserRouter(routes)
