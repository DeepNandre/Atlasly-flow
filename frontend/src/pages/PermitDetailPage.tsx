import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react'
import { usePermitOps, usePermitTimeline, usePermits, usePollPermitStatus, useResolveDrift, useResolveTransition } from '@/hooks/useApi'
import { StatusTimeline } from '@/components/permits/StatusTimeline'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonCard } from '@/components/shared/Skeleton'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function PermitDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const portfolio = usePermits()
  const permitOps = usePermitOps()
  const timeline = usePermitTimeline(id ?? '')
  const pollStatus = usePollPermitStatus()
  const resolveDrift = useResolveDrift()
  const resolveTransition = useResolveTransition()

  const permits = useMemo<Array<Record<string, unknown>>>(() => {
    const projects = ((portfolio.data as { projects?: Array<Record<string, unknown>> } | undefined)?.projects ?? [])
    return projects.flatMap((project) => {
      const permitRows = (project.permits as Array<Record<string, unknown>> | undefined) ?? []
      return permitRows.map((permit) => ({
        ...permit,
        project_name: project.name,
      }))
    })
  }, [portfolio.data])
  const permit = permits.find((row) => String(row.permit_id ?? row.id ?? '') === id) as Record<string, unknown> | undefined
  const timelineItems = ((timeline.data as { timeline?: Array<Record<string, unknown>> } | undefined)?.timeline ?? [])
  const permitOpsData = (permitOps.data as {
    connector_health?: Record<string, unknown>
    transition_review_queue?: { items?: Array<Record<string, unknown>> }
    drift_alerts?: { items?: Array<Record<string, unknown>> }
  } | undefined)
  const transitionItems = (permitOpsData?.transition_review_queue?.items ?? []).filter((item) => String(item.permit_id ?? '') === id)
  const driftAlerts = (permitOpsData?.drift_alerts?.items ?? []).filter((item) => String(item.permit_id ?? '') === id)

  const error = portfolio.error ?? permitOps.error ?? timeline.error
  if (error) return <ErrorState message="Could not load permit" onRetry={() => { portfolio.refetch(); permitOps.refetch(); timeline.refetch() }} />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => navigate('/permits')} className="text-atlasly-muted hover:text-atlasly-ink" aria-label="Back to permits">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-atlasly-ink">{String(permit?.project_name ?? 'Permit')}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            {permit?.status ? <PermitStatusBadge status={String(permit.status)} /> : null}
            <span className="text-sm text-atlasly-muted">{String(permit?.permit_type ?? '').replace(/_/g, ' ') || '—'}</span>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => pollStatus.mutate({ raw_status: 'Under review' })} disabled={pollStatus.isPending}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${pollStatus.isPending ? 'animate-spin' : ''}`} />
          Sync City Status
        </Button>
      </div>

      {transitionItems.map((item) => (
        <div key={String(item.id)} className="rounded-lg border border-atlasly-rust/40 bg-atlasly-rust/5 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-4 w-4 text-atlasly-rust mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-atlasly-rust">Transition requires review</p>
              <p className="text-xs text-atlasly-muted mt-0.5">{String(item.raw_status ?? 'Unmapped status')} needs manual confirmation.</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => resolveTransition.mutate({ review_id: String(item.id), resolution_state: 'resolved' })}>
              Resolve
            </Button>
          </div>
        </div>
      ))}

      {driftAlerts.map((alert) => (
        <div key={String(alert.id)} className="rounded-lg border border-atlasly-warn/40 bg-atlasly-warn/5 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-4 w-4 text-atlasly-warn mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-atlasly-warn">Status drift detected</p>
              <p className="text-xs text-atlasly-muted mt-0.5">{String(alert.reason ?? alert.message ?? 'Portal state differs from Atlasly record.')}</p>
            </div>
            <Button size="sm" variant="outline" onClick={() => resolveDrift.mutate({ alert_id: String(alert.id), status: 'resolved' })}>
              Resolve
            </Button>
          </div>
        </div>
      ))}

      <Card>
        <CardHeader>
          <CardTitle>Permit Status</CardTitle>
        </CardHeader>
        <CardContent>
          {timeline.isLoading ? <SkeletonCard /> : <StatusTimeline currentStatus={String(permit?.status ?? 'draft')} events={timelineItems} />}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Application Details</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                ['Project', String(permit?.project_name ?? '—')],
                ['Permit Type', String(permit?.permit_type ?? '—').replace(/_/g, ' ')],
                ['Normalized Status', String(permit?.status ?? '—')],
                ['Source Status', String(permit?.source_status ?? '—')],
                ['Last Sync', String(permit?.last_sync_at ?? permit?.updated_at ?? '—')],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-4">
                  <span className="text-xs font-medium text-atlasly-muted w-32 shrink-0">{label}</span>
                  <span className="text-sm text-atlasly-ink">{value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Connector Health</CardTitle></CardHeader>
          <CardContent>
            {permitOpsData?.connector_health ? (
              <div className="space-y-3">
                {Object.entries(permitOpsData.connector_health).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-4">
                    <span className="text-sm text-atlasly-ink capitalize">{key.replace(/_/g, ' ')}</span>
                    <span className="text-xs text-atlasly-muted">{String(value ?? '—')}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-atlasly-muted">No connector data</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
