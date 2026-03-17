import { useMemo, useState } from 'react'
import { CheckCircle, Plug, RefreshCw, ShieldAlert, Workflow, XCircle } from 'lucide-react'
import {
  useConnectorCredentials,
  useConnectorSync,
  useCreatePermitBinding,
  useIntegrationsReadiness,
  useLaunchReadiness,
  usePermitBindings,
  usePermits,
  usePollLiveConnector,
  useReadiness,
  useRotateCredentials,
  useSlo,
  useSummary,
  useRuntimeDiagnostics,
  useValidateConnector,
} from '@/hooks/useApi'
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
  const [rotateDialogOpen, setRotateDialogOpen] = useState(false)
  const [rotateTarget, setRotateTarget] = useState('accela_api')
  const [credentialRef, setCredentialRef] = useState('')
  const [bindingPermitId, setBindingPermitId] = useState('')
  const [bindingAhjId, setBindingAhjId] = useState('ca.san_jose.building')
  const [bindingExternalPermitId, setBindingExternalPermitId] = useState('')
  const [livePollOutput, setLivePollOutput] = useState<null | {
    status?: string
    observationsProcessed?: number
    observationsApplied?: number
    observationsReviewed?: number
    unmappedObservations?: number
    operatorMessages: string[]
  }>(null)

  const readinessQuery = useIntegrationsReadiness()
  const runtimeReadiness = useReadiness()
  const runtimeDiagnostics = useRuntimeDiagnostics()
  const slo = useSlo()
  const launchReadiness = useLaunchReadiness()
  const connectorSync = useConnectorSync()
  const livePoll = usePollLiveConnector()
  const validateConnector = useValidateConnector()
  const rotateCredentials = useRotateCredentials()
  const allCredentials = useConnectorCredentials()
  const permitsQuery = usePermits()
  const summaryQuery = useSummary()
  const permitBindings = usePermitBindings(rotateTarget)
  const createPermitBinding = useCreatePermitBinding()

  const readiness = (readinessQuery.data as {
    overall_ready?: boolean
    launch_blockers?: string[]
    warnings?: string[]
    stage2?: Record<string, unknown>
    stage3?: Record<string, unknown>
  } | undefined)
  const stage2 = readiness?.stage2 as Record<string, unknown> | undefined
  const error = readinessQuery.error ?? slo.error ?? launchReadiness.error
  const runtimeWarnings = (
    (summaryQuery.data as { runtime?: { warnings?: string[] } } | undefined)?.runtime?.warnings
      ?? readiness?.warnings
      ?? []
  ) as string[]
  const portfolioProjects = ((permitsQuery.data as { projects?: Array<Record<string, unknown>> } | undefined)?.projects ?? [])
  const permitOptions = portfolioProjects.flatMap((project) =>
    (((project.permits as Array<Record<string, unknown>> | undefined) ?? []).map((permit) => ({
      permitId: String(permit.permit_id ?? permit.id ?? ''),
      label: `${String(project.name ?? 'Project')} - ${String(permit.permit_type ?? 'permit').replace(/_/g, ' ')}`,
    }))),
  )

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
        <p className="text-sm text-atlasly-muted mt-0.5">Connector readiness, credential references, and buyer-safe launch checks</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Hosted Runtime</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {runtimeReadiness.isLoading ? <SkeletonCard /> : (
              <>
                <div className="grid gap-2 text-sm md:grid-cols-2">
                  <div className="rounded-md border border-atlasly-line px-3 py-2">
                    <p className="text-atlasly-muted">Tier</p>
                    <p className="font-medium text-atlasly-ink">{String((runtimeDiagnostics.data as { runtime?: { deployment_tier?: string } } | undefined)?.runtime?.deployment_tier ?? 'unknown')}</p>
                  </div>
                  <div className="rounded-md border border-atlasly-line px-3 py-2">
                    <p className="text-atlasly-muted">Backend</p>
                    <p className="font-medium text-atlasly-ink">{String((runtimeDiagnostics.data as { runtime?: { runtime_backend?: string } } | undefined)?.runtime?.runtime_backend ?? 'unknown')}</p>
                  </div>
                </div>
                <div className="space-y-2 text-xs text-atlasly-muted">
                  {((runtimeReadiness.data as { checks?: Array<{ id?: string; status?: string; detail?: string }> } | undefined)?.checks ?? []).map((check) => (
                    <div key={String(check.id)} className="flex items-center justify-between gap-3 rounded-md border border-atlasly-line px-3 py-2">
                      <span>{String(check.id)}</span>
                      <span className={String(check.status) === 'pass' ? 'text-atlasly-ok' : 'text-atlasly-rust'}>
                        {String(check.status)} {check.detail ? `· ${String(check.detail)}` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Why buyers care</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm text-atlasly-muted">
            <p>Credential readiness proves Atlasly can move beyond PDF parsing into a live permit control tower.</p>
            <p>Permit bindings make the city-facing record auditable instead of hidden in a portal login.</p>
            <p>Validation gives operators an explicit pass/fail answer before they trust live syncs in a pilot.</p>
          </CardContent>
        </Card>
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
                      <div className="text-atlasly-muted mt-1">
                        Updated {formatDate(String(row.updated_at ?? row.created_at ?? ''))}
                        {row.last_validated_at ? ` · Validated ${formatDate(String(row.last_validated_at))}` : ' · Not validated yet'}
                      </div>
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
            {runtimeWarnings.length > 0 ? (
              <div className="rounded-md border border-atlasly-warn/40 bg-atlasly-warn/10 px-3 py-2 text-xs text-atlasly-ink">
                {runtimeWarnings.map((warning) => (
                  <p key={warning}>Warning: {warning}</p>
                ))}
              </div>
            ) : null}
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

      <Card>
        <CardHeader><CardTitle>Connector Validation</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-atlasly-muted">
            Validate the saved connector credential before running a live poll. This checks token shape, app id setup, and whether the connector returns records.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="live_connector">Connector</Label>
              <select
                id="live_connector"
                value={rotateTarget}
                onChange={(event) => setRotateTarget(event.target.value)}
                className="h-10 w-full rounded-md border border-atlasly-line bg-white px-3 text-sm"
              >
                {CONNECTORS.map((connector) => (
                  <option key={connector.key} value={connector.key}>{connector.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="live_ahj">AHJ id</Label>
              <Input id="live_ahj" value={bindingAhjId} onChange={(event) => setBindingAhjId(event.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="live_credential_ref">Credential ref</Label>
              <Input
                id="live_credential_ref"
                value={credentialRef}
                onChange={(event) => setCredentialRef(event.target.value)}
                placeholder="accela_prod_token"
                autoComplete="off"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              onClick={() => {
                validateConnector.mutate(
                  { connector: rotateTarget, ahj_id: bindingAhjId, credential_ref: credentialRef || undefined },
                  {
                    onSuccess: (payload) => {
                      const result = payload as { validation_status?: string; observations_count?: number; operator_message?: string }
                      setLivePollOutput({
                        status: result.validation_status,
                        observationsProcessed: result.observations_count,
                        observationsApplied: undefined,
                        observationsReviewed: undefined,
                        unmappedObservations: undefined,
                        operatorMessages: result.operator_message ? [result.operator_message] : [],
                      })
                    },
                  },
                )
              }}
              disabled={!bindingAhjId.trim() || validateConnector.isPending}
            >
              {validateConnector.isPending ? 'Validating…' : 'Validate Connector'}
            </Button>
            <Button
              onClick={() => {
                livePoll.mutate(
                  {
                    connector: rotateTarget,
                    ahj_id: bindingAhjId,
                    credential_ref: credentialRef || undefined,
                  },
                  {
                    onSuccess: (payload) => {
                      const result = payload as {
                        poll_result?: {
                          run?: { status?: string }
                          observations_processed?: number
                          observations_applied?: number
                          observations_reviewed?: number
                          unmapped_observations?: unknown[]
                        }
                        operator_messages?: string[]
                      }
                      setLivePollOutput({
                        status: result.poll_result?.run?.status,
                        observationsProcessed: result.poll_result?.observations_processed,
                        observationsApplied: result.poll_result?.observations_applied,
                        observationsReviewed: result.poll_result?.observations_reviewed,
                        unmappedObservations: result.poll_result?.unmapped_observations?.length ?? 0,
                        operatorMessages: result.operator_messages ?? [],
                      })
                    },
                  },
                )
              }}
              disabled={!bindingAhjId.trim() || livePoll.isPending}
            >
              {livePoll.isPending ? 'Running…' : 'Run Live Poll'}
            </Button>
            <p className="text-xs text-atlasly-muted">Use an OAuth token-backed secret env, not the Accela app secret. Shovels is optional enrichment.</p>
          </div>
          {livePollOutput ? (
            <div className="rounded-md border border-atlasly-line px-4 py-3 text-sm">
              <div className="grid gap-2 md:grid-cols-5">
                <div><span className="text-atlasly-muted">Status</span><p className="font-medium text-atlasly-ink">{livePollOutput.status ?? 'unknown'}</p></div>
                <div><span className="text-atlasly-muted">Processed</span><p className="font-medium text-atlasly-ink">{livePollOutput.observationsProcessed ?? 0}</p></div>
                <div><span className="text-atlasly-muted">Applied</span><p className="font-medium text-atlasly-ink">{livePollOutput.observationsApplied ?? 0}</p></div>
                <div><span className="text-atlasly-muted">Reviewed</span><p className="font-medium text-atlasly-ink">{livePollOutput.observationsReviewed ?? 0}</p></div>
                <div><span className="text-atlasly-muted">Unmapped</span><p className="font-medium text-atlasly-ink">{livePollOutput.unmappedObservations ?? 0}</p></div>
              </div>
              {livePollOutput.operatorMessages.length > 0 ? (
                <div className="mt-3 space-y-1 text-xs text-atlasly-muted">
                  {livePollOutput.operatorMessages.map((message) => (
                    <p key={message}>• {message}</p>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>External Permit Bindings</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-atlasly-muted">
            Map an Atlasly permit to the external Accela/OpenGov record before running live polling. This is the operator-owned bridge between Atlasly and the city system.
          </p>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="binding_permit">Atlasly permit</Label>
              <select
                id="binding_permit"
                value={bindingPermitId}
                onChange={(event) => setBindingPermitId(event.target.value)}
                className="h-10 w-full rounded-md border border-atlasly-line bg-white px-3 text-sm"
              >
                <option value="">Select permit</option>
                {permitOptions.map((option) => (
                  <option key={option.permitId} value={option.permitId}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="binding_ahj">AHJ id</Label>
              <Input id="binding_ahj" value={bindingAhjId} onChange={(event) => setBindingAhjId(event.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="binding_external">External permit id</Label>
              <Input
                id="binding_external"
                value={bindingExternalPermitId}
                onChange={(event) => setBindingExternalPermitId(event.target.value)}
                placeholder="ALT-12345"
                autoComplete="off"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              onClick={() => {
                createPermitBinding.mutate(
                  {
                    connector: rotateTarget,
                    ahj_id: bindingAhjId,
                    permit_id: bindingPermitId,
                    external_permit_id: bindingExternalPermitId,
                  },
                  {
                    onSuccess: () => {
                      setBindingExternalPermitId('')
                      permitBindings.refetch()
                    },
                  },
                )
              }}
              disabled={!bindingPermitId || !bindingAhjId.trim() || !bindingExternalPermitId.trim() || createPermitBinding.isPending}
            >
              {createPermitBinding.isPending ? 'Saving…' : 'Save Binding'}
            </Button>
            <p className="text-xs text-atlasly-muted">Current connector: {rotateTarget}</p>
          </div>
          <div className="space-y-2">
            {(((permitBindings.data as { items?: Array<Record<string, unknown>> } | undefined)?.items) ?? []).length === 0 ? (
              <p className="text-xs text-atlasly-muted">No bindings saved for this connector yet.</p>
            ) : (
              (((permitBindings.data as { items?: Array<Record<string, unknown>> } | undefined)?.items) ?? []).map((row) => (
                <div key={String(row.id)} className="rounded-md border border-atlasly-line px-3 py-2 text-xs">
                  <div className="font-medium text-atlasly-ink">{String(row.permit_id)} {'->'} {String(row.external_permit_id)}</div>
                  <div className="mt-1 flex items-center justify-between gap-3 text-atlasly-muted">
                    <span>{String(row.connector)} / {String(row.ahj_id)}</span>
                    <span className="inline-flex items-center gap-1 text-atlasly-teal">
                      <Workflow className="h-3.5 w-3.5" />
                      Bound
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

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
