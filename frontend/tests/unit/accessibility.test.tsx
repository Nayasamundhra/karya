import { render } from '@testing-library/react'
import axe from 'axe-core'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { Alert } from '@/components/ui/Alert'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { LoginForm } from '@/features/auth/LoginForm'
import { TestQueryProvider } from './helpers/testQueryClient'

/**
 * jsdom has no real layout/paint engine, so rules that need actual computed
 * colors (`color-contrast`) are unreliable here and disabled — contrast for
 * this palette is checked by hand against WCAG 2.2 AA (see
 * `src/styles/index.css`'s header comment), and a real-browser check
 * belongs in the Playwright suite, not a jsdom unit test.
 */
async function expectNoAxeViolations(container: Element) {
  const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toHaveLength(0)
}

describe('accessibility', () => {
  it('the login form has no detectable accessibility violations', async () => {
    const { container } = render(
      <TestQueryProvider>
        <MemoryRouter>
          <LoginForm />
        </MemoryRouter>
      </TestQueryProvider>,
    )
    await expectNoAxeViolations(container)
  })

  it('core design-system primitives (Button, Input, Badge, Alert) have no detectable violations', async () => {
    const { container } = render(
      <div>
        <Button>Primary action</Button>
        <Button variant="secondary">Secondary action</Button>
        <Input label="Employee code" hint="As assigned by your administrator" />
        <Badge variant="success">Checked in</Badge>
        <Alert variant="danger" title="Something went wrong">
          Please try again.
        </Alert>
      </div>,
    )
    await expectNoAxeViolations(container)
  })
})
