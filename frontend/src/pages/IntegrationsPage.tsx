import { useState } from 'react'
import { Plug, RefreshCw, CheckCircle, XCircle } from 'lucide-react'
import { useIntegrationsReadiness, useSlo, useConnectorSync, useRotateCredentials } from '@/hooks/useApi'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonCard } from '@/components/shared/Skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/utils'

const CONNECTORS = [
  { key: 'accela', label: 'Accela', description: 'City permitting platform integration' },
  { key: 'opengov', label: 'OpenGov', description: 'Government financial portal' },
  { key: 'shovels', label: 'Shovels', description: 'AHJ jurisdiction lookup' },
  { key: 'stripe', label: 'Stripe', description: 'Payment processing' },
]

export default function IntegrationsPage() {
  const { data, isLoading, error, refetch } = useIntegrationsReadiness()
  const slo = useSlo()
  const connectorSync = useConnectorSync()
  const rotateCredentials = useRotateCredentials()

  const [rotateDialogOpen, setRotateDialogOpen] = useState(false)
  const [rotateTarget, setRotateTarget] = useState('')
  const [newCredential, setNewCredential] = useState('')

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const readiness: Record<string, any> = (data as Record<string, any>) ?? {}

  if (error) return <ErrorState message="Could not load integrations" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Integrations</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Connect Atlasly to your city portals and payment processors</p>
      </div>

      {/* Connector cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : Object.keys(readiness).length === 0 && !isLoading ? (
          <div className="md:col-span-2">
            <EmptyState
              icon={Plug}
              title="No connectors configured"
              description="Connect to city portals and payment processors to automate permit tracking"
            />
          </div>
        ) : (
          CONNECTORS.map((conn) => {
            const status = readiness[conn.key] ?? readiness[`${conn.key}_status`]
            const isConnected = status === 'ok' || status === 'connected' || status === true
            const lastSync = readiness[`${conn.key}_last_sync`]

            return (
              <Card key={conn.key}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-atlasly-ink">{conn.label}</h3>
                        <div className={cn('flex items-center gap-1 text-xs font-medium', isConnected ? 'text-atlasly-ok' : 'text-atlasly-bad')}>
                          {isConnected ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                          {isConnected ? 'Connected' : 'Not configured'}
                        </div>
                      </div>
                      <p className="text-xs text-atlasly-muted mt-0.5">{conn.description}</p>
                      {lastSync && <p className="text-xs text-atlasly-muted mt-1">Last sync: {formatDate(lastSync)}</p>}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => connectorSync.mutate({ connector: conn.key }, { onSuccess: () => { refetch() } })}
                        disabled={connectorSync.isPending}
                        title="Sync now"
                      >
                        <RefreshCw className={`h-3.5 w-3.5 ${connectorSync.isPending ? 'animate-spin' : ''}`} />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => { setRotateTarget(conn.key); setRotateDialogOpen(true) }}
                      >
                        Rotate Key
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })
        )}
      </div>

      {/* SLO card */}
      {slo.data != null && (
        <Card>
          <CardHeader><CardTitle>Service Level Overview</CardTitle></CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {(Object.entries(slo.data as Record<string, unknown>)).slice(0, 8).map(([k, v]) => (
                <div key={k}>
                  <p className="text-xs text-atlasly-muted capitalize">{k.replace(/_/g, ' ')}</p>
                  <p className="text-sm font-semibold text-atlasly-ink mt-0.5">{String(v)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Rotate credentials dialog */}
      <Dialog open={rotateDialogOpen} onOpenChange={setRotateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rotate {rotateTarget} Credentials</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="credential">New API Key / Credential</Label>
              <Input
                id="credential"
                type="password"
                value={newCredential}
                onChange={(e) => setNewCredential(e.target.value)}
                placeholder="Paste new credential here"
              />
            </div>
            <Button
              onClick={() => {
                rotateCredentials.mutate(
                  { connector: rotateTarget, credential: newCredential },
                  {
                    onSuccess: () => {
                      setRotateDialogOpen(false)
                      setNewCredential('')
                      refetch()
                    },
                  },
                )
              }}
              disabled={!newCredential || rotateCredentials.isPending}
            >
              {rotateCredentials.isPending ? 'Rotating…' : 'Rotate Credentials'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
