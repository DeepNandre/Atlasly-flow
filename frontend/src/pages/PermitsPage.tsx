import { useState } from 'react'
import { Plus, Building2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { usePermits } from '@/hooks/useApi'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PermitIntakeWizard } from '@/components/permits/PermitIntakeWizard'
import { formatDate } from '@/lib/utils'

export default function PermitsPage() {
  const { data, isLoading, error, refetch } = usePermits()
  const [intakeOpen, setIntakeOpen] = useState(false)
  const navigate = useNavigate()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const permits: any[] = (data as any)?.permits ?? (Array.isArray(data) ? data : [])

  if (error) return <ErrorState message="Could not load permits" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Permits</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Track and manage your permit applications</p>
        </div>
        <Button onClick={() => setIntakeOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          New Permit
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All Permits</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={5} /></div>
          ) : permits.length === 0 ? (
            <EmptyState
              icon={Building2}
              title="No permits yet"
              description="Start a new permit application to track it through the approval process"
              actionLabel="New Permit"
              onAction={() => setIntakeOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-atlasly-line">
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Project</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Type</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">AHJ</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {permits.map((p) => {
                    const id = p.permit_id ?? p.id
                    return (
                      <tr
                        key={id}
                        className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50 cursor-pointer"
                        onClick={() => navigate(`/permits/${id}`)}
                      >
                        <td className="px-5 py-3 font-medium text-atlasly-ink">{p.project_name ?? p.name ?? '—'}</td>
                        <td className="px-5 py-3 text-atlasly-muted">
                          {(p.permit_type ?? p.type ?? '').replace(/_/g, ' ') || '—'}
                        </td>
                        <td className="px-5 py-3">
                          <PermitStatusBadge status={p.status ?? 'draft'} />
                        </td>
                        <td className="px-5 py-3 text-atlasly-muted">{p.ahj_name ?? p.jurisdiction ?? '—'}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(p.updated_at)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={intakeOpen} onOpenChange={setIntakeOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>New Permit Application</DialogTitle>
          </DialogHeader>
          <PermitIntakeWizard onSuccess={() => { setIntakeOpen(false); refetch() }} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
