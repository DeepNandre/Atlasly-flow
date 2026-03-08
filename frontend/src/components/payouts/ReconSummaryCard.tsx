import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useReconcile } from '@/hooks/useApi'

interface ReconSummaryCardProps {
  data: {
    state_breakdown?: Record<string, number>
    runs?: unknown[]
    pending_outbox?: number
  }
  onSuccess?: () => void
}

export function ReconSummaryCard({ data, onSuccess }: ReconSummaryCardProps) {
  const reconcile = useReconcile()
  const stateBreakdown = data.state_breakdown ?? {}

  const stats = [
    { label: 'Created', value: stateBreakdown.created ?? 0 },
    { label: 'Submitted', value: stateBreakdown.submitted ?? 0 },
    { label: 'Settled', value: stateBreakdown.settled ?? 0 },
    { label: 'Reversed', value: stateBreakdown.reversed ?? 0 },
    { label: 'Pending Outbox', value: data.pending_outbox ?? 0 },
  ]

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Reconciliation</CardTitle>
        <Button size="sm" variant="outline" onClick={() => reconcile.mutate(undefined, { onSuccess })} disabled={reconcile.isPending}>
          {reconcile.isPending ? 'Running…' : 'Run Reconciliation'}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {stats.map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs text-atlasly-muted">{label}</p>
              <p className="text-lg font-bold text-atlasly-ink mt-0.5">{value}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
