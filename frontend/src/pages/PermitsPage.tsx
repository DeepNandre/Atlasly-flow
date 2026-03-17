import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Building2, Plus } from 'lucide-react'
import { usePermitOps, usePermits } from '@/hooks/useApi'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PermitIntakeWizard } from '@/components/permits/PermitIntakeWizard'
import { formatDate } from '@/lib/utils'

export default function PermitsPage() {
  const { data, isLoading, error, refetch } = usePermits()
  const permitOps = usePermitOps()
  const [intakeOpen, setIntakeOpen] = useState(false)
  const navigate = useNavigate()

  const permits = useMemo<Array<Record<string, unknown>>>(() => {
    const projects = ((data as { projects?: Array<Record<string, unknown>> } | undefined)?.projects ?? [])
    return projects.flatMap((project) => {
      const projectName = String(project.name ?? 'Project')
      const projectCode = String(project.project_code ?? '')
      const permitRows = (project.permits as Array<Record<string, unknown>> | undefined) ?? []
      return permitRows.map((permit) => ({
        ...permit,
        project_name: projectName,
        project_code: projectCode,
        address: project.address,
      }))
    })
  }, [data])

  const transitionQueue = ((permitOps.data as { transition_review_queue?: { open_count?: number } } | undefined)?.transition_review_queue?.open_count ?? 0)
  const driftOpen = ((permitOps.data as { drift_alerts?: { open_count?: number } } | undefined)?.drift_alerts?.open_count ?? 0)

  if (error || permitOps.error) return <ErrorState message="Could not load permits" onRetry={() => { refetch(); permitOps.refetch() }} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Permits</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Track applications, sync health, and review status drift</p>
        </div>
        <Button onClick={() => setIntakeOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          New Permit
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Transition Review Queue</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold text-atlasly-ink">{transitionQueue}</p>
            <p className="text-sm text-atlasly-muted mt-1">Statuses waiting for manual normalization review</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Open Drift Alerts</CardTitle></CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-atlasly-warn" />
              <div>
                <p className="text-3xl font-semibold text-atlasly-ink">{driftOpen}</p>
                <p className="text-sm text-atlasly-muted mt-1">Permits with unresolved portal drift</p>
              </div>
            </div>
          </CardContent>
        </Card>
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
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Binding</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Source Status</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {permits.map((permit) => {
                    const record = permit as Record<string, unknown>
                    const permitId = String(record.permit_id ?? record.id)
                    return (
                      <tr
                        key={permitId}
                        className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50 cursor-pointer"
                        onClick={() => navigate(`/permits/${permitId}`)}
                      >
                        <td className="px-5 py-3 font-medium text-atlasly-ink">{String(record.project_name ?? '—')}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{String(record.permit_type ?? '').replace(/_/g, ' ') || '—'}</td>
                        <td className="px-5 py-3"><PermitStatusBadge status={String(record.status ?? 'draft')} /></td>
                        <td className="px-5 py-3 text-atlasly-muted">{String(record.binding_status ?? 'unmapped')}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{String(record.source_status ?? '—')}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(String(record.updated_at ?? record.last_sync_at ?? ''))}</td>
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
          <PermitIntakeWizard onSuccess={() => { setIntakeOpen(false); refetch(); permitOps.refetch() }} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
