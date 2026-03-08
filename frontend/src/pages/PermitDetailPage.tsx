import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, RefreshCw, AlertTriangle } from 'lucide-react'
import { usePermits, usePermitTimeline, usePollPermitStatus, useResolveDrift } from '@/hooks/useApi'
import { StatusTimeline } from '@/components/permits/StatusTimeline'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonCard } from '@/components/shared/Skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export default function PermitDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, isLoading, error, refetch } = usePermits()
  const timeline = usePermitTimeline(id ?? '')
  const pollStatus = usePollPermitStatus()
  const resolveDrift = useResolveDrift()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const permits: any[] = (data as any)?.permits ?? (Array.isArray(data) ? data : [])
  const permit = permits.find((p) => (p.permit_id ?? p.id) === id)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const events: any[] = (timeline.data as any)?.events ?? []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const driftAlerts: any[] = permit?.drift_alerts ?? []

  if (error) return <ErrorState message="Could not load permit" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/permits')} className="text-atlasly-muted hover:text-atlasly-ink">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-atlasly-ink">
            {permit?.project_name ?? permit?.name ?? 'Permit'}
          </h1>
          <div className="flex items-center gap-2 mt-0.5">
            {permit?.status && <PermitStatusBadge status={permit.status} />}
            <span className="text-sm text-atlasly-muted">{permit?.permit_type?.replace(/_/g, ' ')}</span>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => id && pollStatus.mutate({ permit_id: id }, { onSuccess: () => { refetch() } })}
          disabled={pollStatus.isPending}
        >
          <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${pollStatus.isPending ? 'animate-spin' : ''}`} />
          Sync City Status
        </Button>
      </div>

      {/* Drift alerts */}
      {driftAlerts.map((alert, i) => (
        <div key={i} className="rounded-lg border border-atlasly-warn/40 bg-atlasly-warn/5 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-4 w-4 text-atlasly-warn mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-atlasly-warn">{alert.title ?? 'Status drift detected'}</p>
              <p className="text-xs text-atlasly-muted mt-0.5">{alert.description ?? alert.message}</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => id && resolveDrift.mutate({ permit_id: id, resolution: 'acknowledged' }, { onSuccess: () => { refetch() } })}
              disabled={resolveDrift.isPending}
            >
              Resolve
            </Button>
          </div>
        </div>
      ))}

      {/* Status timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Permit Status</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonCard />
          ) : (
            <StatusTimeline currentStatus={permit?.status} events={events} />
          )}
        </CardContent>
      </Card>

      {/* Details grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Application Details</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                ['Address', permit?.address],
                ['AHJ', permit?.ahj_name ?? permit?.jurisdiction],
                ['Permit Type', permit?.permit_type?.replace(/_/g, ' ')],
                ['Valuation', permit?.valuation ? `$${Number(permit.valuation).toLocaleString()}` : undefined],
                ['Application Number', permit?.application_number ?? permit?.permit_number],
              ].map(([label, value]) => (
                <div key={label} className="flex gap-4">
                  <span className="text-xs font-medium text-atlasly-muted w-32 shrink-0">{label}</span>
                  <span className="text-sm text-atlasly-ink">{value ?? '—'}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Connector Health</CardTitle></CardHeader>
          <CardContent>
            {permit?.connector_status ? (
              <div className="space-y-3">
                {Object.entries(permit.connector_status).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between">
                    <span className="text-sm text-atlasly-ink capitalize">{k.replace(/_/g, ' ')}</span>
                    <span className={`text-xs font-medium ${v === 'ok' || v === 'connected' ? 'text-atlasly-ok' : 'text-atlasly-bad'}`}>
                      {String(v)}
                    </span>
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
