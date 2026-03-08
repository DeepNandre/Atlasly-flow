import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useReconcile } from '@/hooks/useApi'

interface ReconSummaryCardProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any
  onSuccess?: () => void
}

export function ReconSummaryCard({ data, onSuccess }: ReconSummaryCardProps) {
  const reconcile = useReconcile()

  const stats = [
    { label: 'Total Payouts', value: data?.total_payouts ?? '—' },
    { label: 'Settled', value: data?.settled ?? '—' },
    { label: 'Pending', value: data?.pending ?? '—' },
    { label: 'Reversed', value: data?.reversed ?? '—' },
    { label: 'Total Amount', value: data?.total_amount ? `$${Number(data.total_amount).toLocaleString()}` : '—' },
  ]

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Reconciliation</CardTitle>
        <Button
          size="sm"
          variant="outline"
          onClick={() => reconcile.mutate({}, { onSuccess })}
          disabled={reconcile.isPending}
        >
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
