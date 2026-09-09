import { useState } from 'react'
import { MonitorSmartphone, Plus } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { ConfirmationDialog } from '@/components/ui/ConfirmationDialog'
import { EmptyState } from '@/components/feedback/EmptyState'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/Table'
import { CreateDisplayTokenDialog } from '@/features/display/CreateDisplayTokenDialog'
import { useDisplayTokens } from '@/features/display/useDisplayTokens'
import { useRevokeDisplayToken } from '@/features/display/useDisplayTokenMutations'
import { useLocation } from '@/features/tenant/useLocation'
import { describeError } from '@/lib/errors/describeError'
import type { DisplayTokenResponse } from '@/lib/api/types'
import { toast } from '@/stores/toastStore'

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function DisplayTokensCard() {
  const { data, isLoading, isError, error, refetch } = useDisplayTokens()
  const revokeToken = useRevokeDisplayToken()
  const [createOpen, setCreateOpen] = useState(false)
  const [revokeTarget, setRevokeTarget] = useState<DisplayTokenResponse | null>(null)

  // The backend refuses to mint a display token before a location exists
  // (409) - this is the proactive version of that same rule, so a caller
  // is told why *before* opening the dialog rather than after submitting
  // into a generic error. `location === undefined` (still loading) is
  // treated as "don't know yet", never as "missing" - see `useLocation`.
  const { data: location, isLoading: isLocationLoading } = useLocation()
  const hasNoLocation = !isLocationLoading && location === null

  async function handleRevokeConfirmed() {
    if (!revokeTarget) return
    try {
      await revokeToken.mutateAsync(revokeTarget.id)
      toast.success('Display revoked', `${revokeTarget.label} can no longer scan employees in.`)
    } catch (err) {
      toast.error('Could not revoke display', describeError(err).message)
    } finally {
      setRevokeTarget(null)
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle>Office displays</CardTitle>
            <CardDescription>
              Each row is one physical screen showing the check-in QR code. Revoking one takes effect
              immediately.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setCreateOpen(true)} disabled={hasNoLocation}>
            <Plus className="size-4" aria-hidden="true" />
            New display
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading && <Skeleton className="h-11 w-full" />}
          {isError && <ErrorState error={error} onRetry={() => void refetch()} />}
          {hasNoLocation && (
            <EmptyState
              icon={MonitorSmartphone}
              title="Set up an attendance location first"
              description="A display scans people into a place, so your organization's attendance location needs to be set up before you can add one."
            />
          )}
          {!hasNoLocation && data && data.items.length === 0 && (
            <EmptyState
              icon={MonitorSmartphone}
              title="No displays yet"
              description='Create one, then open "/display" on the screen at your entrance.'
            />
          )}
          {data && data.items.length > 0 && (
            <>
              {/* Desktop table — genuinely tabular, per Table's own header
               * comment. On mobile the primary action (Revoke) would sit
               * off the visible edge of a horizontally-scrolled table, so
               * this list gets its own card layout instead, same pattern
               * as `TeamAttendanceTable`. */}
              <div className="hidden md:block">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Last used</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium text-foreground">{item.label}</TableCell>
                        <TableCell>{formatDate(item.created_at)}</TableCell>
                        <TableCell>{item.last_used_at ? formatDate(item.last_used_at) : 'Never'}</TableCell>
                        <TableCell>
                          {item.revoked_at ? (
                            <Badge variant="danger">Revoked</Badge>
                          ) : (
                            <Badge variant="success">Active</Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          {!item.revoked_at && (
                            <Button variant="secondary" size="sm" onClick={() => setRevokeTarget(item)}>
                              Revoke
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <ul className="flex flex-col gap-2 md:hidden">
                {data.items.map((item) => (
                  <li key={item.id} className="rounded-lg border border-border p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-foreground">{item.label}</p>
                        <p className="mt-0.5 text-xs text-foreground-muted">
                          Created {formatDate(item.created_at)}
                        </p>
                        <p className="text-xs text-foreground-muted">
                          Last used {item.last_used_at ? formatDate(item.last_used_at) : 'Never'}
                        </p>
                      </div>
                      {item.revoked_at ? (
                        <Badge variant="danger">Revoked</Badge>
                      ) : (
                        <Badge variant="success">Active</Badge>
                      )}
                    </div>
                    {!item.revoked_at && (
                      <Button
                        variant="secondary"
                        size="sm"
                        className="mt-3 w-full"
                        onClick={() => setRevokeTarget(item)}
                      >
                        Revoke
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>

      <CreateDisplayTokenDialog open={createOpen} onOpenChange={setCreateOpen} />

      {revokeTarget && (
        <ConfirmationDialog
          open
          onOpenChange={(open) => !open && setRevokeTarget(null)}
          title="Revoke this display?"
          description={`${revokeTarget.label} will immediately stop being able to show a scannable QR code. This can't be undone — you'd need to set up a new display.`}
          confirmLabel="Revoke"
          confirmVariant="destructive"
          onConfirm={handleRevokeConfirmed}
        />
      )}
    </>
  )
}
