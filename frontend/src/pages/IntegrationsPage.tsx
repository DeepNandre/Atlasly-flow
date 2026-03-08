import { useMemo, useState } from 'react'
import { CheckCircle, Plug, RefreshCw, ShieldAlert, XCircle } from 'lucide-react'
import { useConnectorCredentials, useConnectorSync, useIntegrationsReadiness, useLaunchReadiness, useRotateCredentials, useSlo } from '@/hooks/useApi'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonCard } from '@/components/shared/Skeleton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatDate } from '@/lib/utils'

const CONNECTORS = [
  { key: 'accela_api', label: 'Accela', description: 'Legacy city permitting portal connector' },
  { key: 'opengov_api', label: 'OpenGov', description: 'Modern municipal workflow connector' },
]

export default function IntegrationsPage() {
  const readinessQuery = useIntegrationsReadiness()
  const slo = useSlo()
  const launchReadiness = useLaunchReadiness()
  const connectorSync = useConnectorSync()
  const rotateCredentials = useRotateCredentials()
  const allCredentials = useConnectorCredentials()

  const [rotateDialogOpen, setRotateDialogOpen] = useState(false)
  const [rotateTarget, setRotateTarget] = useState('accela_api')
  const [credentialRef, setCredentialRef] = useState('')

  const readiness = (readinessQuery.data as {
    overall_ready?: boolean
    launch_blockers?: string[]
    stage2?: Record<string, unknown>
    stage3?: Record<string, unknown>
  } | undefined)
  const stage2 = readiness?.stage2 as Record<string, unknown> | undefined
  const error = readinessQuery.error ?? slo.error ?? launchReadiness.error

  const connectorCards = useMemo(() => {
    const credentials = ((allCredentials.data as { items?: Array<Record<string, unknown>> } | undefined)?.items ?? [])
    return CONNECTORS.map((connector) => {
      const connectorState = (stage2?.[connector.key] as Record<string, unknown> | undefined) ?? {}
      const connectorCredentials = credentials.filter((row) => String(row.connector ?? '') === connector.key)
      return {
        ...connector,
        ready: Boolean(connectorState.ready),
        configuredCredentials: Number(connectorState.configured_credentials ?? 0),
        missingSecretEnvs: (connectorState.missing_secret_envs as string[] | undefined) ?? [],
        credentials: connectorCredentials,
      }
    })
  }, [allCredentials.data, stage2])

  if (error) return <ErrorState message="Could not load integrations" onRetry={() => { readinessQuery.refetch(); slo.refetch(); launchReadiness.refetch() }} />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Integrations</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Connector readiness, credential references, and operational launch checks</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {readinessQuery.isLoading ? (
          Array.from({ length: 2 }).map((_, index) => <SkeletonCard key={index} />)
        ) : connectorCards.length === 0 ? (
          <div className="md:col-span-2">
            <EmptyState icon={Plug} title="No connectors configured" description="Add credential references to start live city syncs." />
          </div>
        ) : connectorCards.map((connector) => (
          <Card key={connector.key}>
            <CardContent className="p-5 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-atlasly-ink">{connector.label}</h3>
                    <div className={`flex items-center gap-1 text-xs font-medium ${connector.ready ? 'text-atlasly-ok' : 'text-atlasly-bad'}`}>
                      {connector.ready ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                      {connector.ready ? 'Ready' : 'Needs setup'}
                    </div>
                  </div>
                  <p className="text-xs text-atlasly-muted mt-0.5">{connector.description}</p>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => connectorSync.mutate({ connector_name: connector.key, run_mode: 'delta' }, { onSuccess: () => readinessQuery.refetch() })}
                  disabled={connectorSync.isPending}
                  aria-label={`Sync ${connector.label}`}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${connectorSync.isPending ? 'animate-spin' : ''}`} />
                </Button>
              </div>

              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-atlasly-muted">Credential refs</span>
                  <span className="text-atlasly-ink">{connector.configuredCredentials}</span>
                </div>
                <div className="flex items-start justify-between gap-3">
                  <span className="text-atlasly-muted">Missing env vars</span>
                  <span className="text-right text-xs text-atlasly-ink">{connector.missingSecretEnvs.length ? connector.missingSecretEnvs.join(', ') : 'None'}</span>
                </div>
              </div>

              <div className="space-y-2">
                {connector.credentials.length === 0 ? (
                  <p className="text-xs text-atlasly-muted">No credential references stored yet.</p>
                ) : connector.credentials.map((row) => (
                  <div key={String(row.id)} className="rounded-md border border-atlasly-line px-3 py-2 text-xs">
                    <div className="font-mono text-atlasly-ink">{String(row.credential_ref ?? '—')}</div>
                    <div className="text-atlasly-muted mt-1">Updated {formatDate(String(row.updated_at ?? row.created_at ?? ''))}</div>
                  </div>
                ))}
              </div>

              <Button size="sm" variant="outline" onClick={() => { setRotateTarget(connector.key); setRotateDialogOpen(true) }}>
                Update Credential Ref
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Launch Readiness</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className={`flex items-center gap-2 text-sm font-medium ${readiness?.overall_ready ? 'text-atlasly-ok' : 'text-atlasly-rust'}`}>
              <ShieldAlert className="h-4 w-4" />
              {readiness?.overall_ready ? 'Ready for live credentials' : 'Blocked by missing setup'}
            </div>
            <div className="space-y-2 text-sm text-atlasly-muted">
              {((launchReadiness.data as { blockers?: string[] } | undefined)?.blockers ?? readiness?.launch_blockers ?? []).map((blocker) => (
                <p key={blocker}>• {blocker}</p>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Operational SLO</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {slo.data ? (
              Object.entries((slo.data as Record<string, unknown>) ?? {})
                .filter(([, value]) => value !== null && value !== undefined && typeof value !== 'object')
                .map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-4 text-sm">
                    <span className="text-atlasly-muted capitalize">{key.replace(/_/g, ' ')}</span>
                    <span className="text-atlasly-ink">{String(value)}</span>
                  </div>
                ))
            ) : (
              <p className="text-sm text-atlasly-muted">No SLO data yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={rotateDialogOpen} onOpenChange={setRotateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Update Credential Reference</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="credential_ref">Credential ref</Label>
              <Input
                id="credential_ref"
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder="accela_prod_token"
                autoComplete="off"
              />
              <p className="text-xs text-atlasly-muted">Atlasly stores the reference only. The actual secret must exist in the matching environment variable.</p>
            </div>
            <Button
              onClick={() => {
                rotateCredentials.mutate(
                  { connector: rotateTarget, credential_ref: credentialRef },
                  {
                    onSuccess: () => {
                      setRotateDialogOpen(false)
                      setCredentialRef('')
                      readinessQuery.refetch()
                      allCredentials.refetch()
                    },
                  },
                )
              }}
              disabled={!credentialRef.trim() || rotateCredentials.isPending}
            >
              {rotateCredentials.isPending ? 'Saving…' : 'Save Credential Ref'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
