import { useState } from 'react'
import { Plus, DollarSign, ChevronDown, ChevronRight } from 'lucide-react'
import { useFinanceOps, usePayoutOutbox, usePublishOutbox } from '@/hooks/useApi'
import { PayoutStatusBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { PayoutForm } from '@/components/payouts/PayoutForm'
import { ReconSummaryCard } from '@/components/payouts/ReconSummaryCard'
import { formatDate } from '@/lib/utils'

export default function PayoutsPage() {
  const { data, isLoading, error, refetch } = useFinanceOps()
  const outbox = usePayoutOutbox()
  const publishOutbox = usePublishOutbox()
  const [createOpen, setCreateOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const payouts: any[] = (data as any)?.payouts ?? (Array.isArray(data) ? data : [])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recon = (data as any)?.reconciliation ?? (data as any)?.summary

  if (error) return <ErrorState message="Could not load payouts" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Payouts</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Manage contractor payments and reconciliation</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Create Payout
        </Button>
      </div>

      {recon && <ReconSummaryCard data={recon} onSuccess={refetch} />}

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
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Recipient</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Amount</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Permit</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {payouts.map((p) => {
                    const id = p.payout_id ?? p.id
                    return (
                      <tr key={id} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40">
                        <td className="px-5 py-3 font-medium text-atlasly-ink">{p.recipient ?? p.payee ?? '—'}</td>
                        <td className="px-5 py-3 text-atlasly-ink font-mono">
                          {p.amount ? `$${Number(p.amount).toLocaleString()}` : '—'}
                        </td>
                        <td className="px-5 py-3"><PayoutStatusBadge status={p.state ?? p.status ?? 'created'} /></td>
                        <td className="px-5 py-3 text-atlasly-muted text-xs font-mono">{p.permit_id ?? '—'}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(p.created_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Advanced: outbox */}
      <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 text-sm font-medium text-atlasly-muted hover:text-atlasly-ink">
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
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {((outbox.data as any)?.events ?? []).length === 0 ? (
                <p className="text-sm text-atlasly-muted">Outbox is empty</p>
              ) : (
                <p className="text-sm text-atlasly-muted">
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {(outbox.data as any)?.events?.length} pending events
                </p>
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
