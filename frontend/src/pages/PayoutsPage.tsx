import { useState } from 'react'
import { ChevronDown, ChevronRight, DollarSign, Plus } from 'lucide-react'
import { useFinanceOps, usePayoutOutbox, usePublishOutbox, useReconcile } from '@/hooks/useApi'
import { PayoutForm } from '@/components/payouts/PayoutForm'
import { ReconSummaryCard } from '@/components/payouts/ReconSummaryCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { PayoutStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatDate } from '@/lib/utils'

export default function PayoutsPage() {
  const { data, isLoading, error, refetch } = useFinanceOps()
  const outbox = usePayoutOutbox()
  const publishOutbox = usePublishOutbox()
  const reconcile = useReconcile()
  const [createOpen, setCreateOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const payload = (data as {
    payouts?: { recent_instructions?: Array<Record<string, unknown>>; state_breakdown?: Record<string, number> }
    reconciliation?: Record<string, unknown>
    outbox?: Record<string, unknown>
  } | undefined)
  const payouts = payload?.payouts?.recent_instructions ?? []
  const outboxEvents = ((outbox.data as { events?: Array<Record<string, unknown>> } | undefined)?.events ?? [])

  if (error) return <ErrorState message="Could not load payouts" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Payouts</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Manage milestone payout instructions and reconciliation</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Create Payout
        </Button>
      </div>

      <ReconSummaryCard data={{
        ...(payload?.reconciliation ?? {}),
        state_breakdown: payload?.payouts?.state_breakdown ?? {},
        pending_outbox: Number(payload?.outbox?.pending_count ?? 0),
      }} onSuccess={() => reconcile.mutate(undefined, { onSuccess: () => refetch() })} />

      <Card>
        <CardHeader><CardTitle>Payout Instructions</CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={5} /></div>
          ) : payouts.length === 0 ? (
            <EmptyState
              icon={DollarSign}
              title="No payouts yet"
              description="Create a payout instruction once a permit milestone is reached"
              actionLabel="Create Payout"
              onAction={() => setCreateOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-atlasly-line">
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Beneficiary</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Amount</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Permit</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {payouts.map((payout) => (
                    <tr key={String(payout.instruction_id ?? payout.id)} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40">
                      <td className="px-5 py-3 font-medium text-atlasly-ink">{String(payout.beneficiary_id ?? payout.recipient ?? '—')}</td>
                      <td className="px-5 py-3 text-atlasly-ink font-mono">{typeof payout.amount === 'number' ? `$${Number(payout.amount).toLocaleString()}` : '—'}</td>
                      <td className="px-5 py-3"><PayoutStatusBadge status={String(payout.instruction_state ?? payout.status ?? 'created')} /></td>
                      <td className="px-5 py-3 text-atlasly-muted text-xs font-mono">{String(payout.permit_id ?? '—')}</td>
                      <td className="px-5 py-3 text-atlasly-muted">{formatDate(String(payout.created_at ?? ''))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className="flex items-center gap-2 text-sm font-medium text-atlasly-muted hover:text-atlasly-ink">
            {advancedOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Advanced — Outbox
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <Card className="mt-3">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle>Event Outbox</CardTitle>
              <Button size="sm" variant="outline" onClick={() => publishOutbox.mutate()} disabled={publishOutbox.isPending}>
                {publishOutbox.isPending ? 'Publishing…' : 'Publish Outbox'}
              </Button>
            </CardHeader>
            <CardContent>
              {outboxEvents.length === 0 ? (
                <p className="text-sm text-atlasly-muted">Outbox is empty</p>
              ) : (
                <p className="text-sm text-atlasly-muted">{outboxEvents.length} pending events</p>
              )}
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Payout Instruction</DialogTitle>
          </DialogHeader>
          <PayoutForm onSuccess={() => { setCreateOpen(false); refetch() }} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
