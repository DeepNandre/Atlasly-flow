import { useState } from 'react'
import { useApiKeys, useAuditExport, useCreateApiKey, useCreateWebhook, useRuntimeDiagnostics, useTaskTemplates, useWebhooks } from '@/hooks/useApi'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate } from '@/lib/utils'

export default function SettingsPage() {
  const webhooks = useWebhooks()
  const createWebhook = useCreateWebhook()
  const apiKeys = useApiKeys()
  const createApiKey = useCreateApiKey()
  const auditExport = useAuditExport()
  const taskTemplates = useTaskTemplates()
  const runtimeDiagnostics = useRuntimeDiagnostics()

  const [webhookUrl, setWebhookUrl] = useState('')
  const [keyName, setKeyName] = useState('')

  const error = webhooks.error ?? apiKeys.error ?? taskTemplates.error
  if (error) return <ErrorState message="Could not load settings" onRetry={() => { webhooks.refetch(); apiKeys.refetch(); taskTemplates.refetch() }} />

  const webhookRows = ((webhooks.data as { webhooks?: Array<Record<string, unknown>> } | undefined)?.webhooks ?? [])
  const keyRows = ((apiKeys.data as { keys?: Array<Record<string, unknown>> } | undefined)?.keys ?? [])
  const templateRows = ((taskTemplates.data as { templates?: Array<Record<string, unknown>> } | undefined)?.templates ?? [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Settings</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Manage enterprise webhooks, API keys, templates, and audit exports</p>
      </div>

      {((runtimeDiagnostics.data as { readiness?: { warnings?: string[]; blockers?: string[] } } | undefined)?.readiness) ? (
        <Card>
          <CardHeader><CardTitle>Runtime Warnings</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm text-atlasly-muted">
            {(((runtimeDiagnostics.data as { readiness?: { blockers?: string[] } }).readiness?.blockers) ?? []).length > 0 ? (
              <div className="rounded-md border border-atlasly-rust/30 bg-atlasly-rust/5 px-3 py-2 text-atlasly-ink">
                {((runtimeDiagnostics.data as { readiness?: { blockers?: string[] } }).readiness?.blockers ?? []).map((blocker) => (
                  <p key={blocker}>Blocker: {blocker}</p>
                ))}
              </div>
            ) : null}
            {(((runtimeDiagnostics.data as { readiness?: { warnings?: string[] } }).readiness?.warnings) ?? []).length > 0 ? (
              <div className="rounded-md border border-atlasly-warn/30 bg-atlasly-warn/10 px-3 py-2 text-atlasly-ink">
                {((runtimeDiagnostics.data as { readiness?: { warnings?: string[] } }).readiness?.warnings ?? []).map((warning) => (
                  <p key={warning}>Warning: {warning}</p>
                ))}
              </div>
            ) : (
              <p>No runtime warnings. Hosted settings are in a clean state.</p>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Tabs defaultValue="webhooks">
        <TabsList>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="api-keys">API Keys</TabsTrigger>
          <TabsTrigger value="templates">Task Templates</TabsTrigger>
          <TabsTrigger value="audit">Audit Exports</TabsTrigger>
        </TabsList>

        <TabsContent value="webhooks" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Webhook Subscriptions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <Input
                  value={webhookUrl}
                  onChange={(event) => setWebhookUrl(event.target.value)}
                  placeholder="https://your-server.com/webhook"
                  className="flex-1"
                  autoComplete="url"
                />
                <Button
                  onClick={() => createWebhook.mutate({ target_url: webhookUrl }, { onSuccess: () => { setWebhookUrl(''); webhooks.refetch() } })}
                  disabled={!webhookUrl || createWebhook.isPending}
                >
                  {createWebhook.isPending ? 'Adding…' : 'Add'}
                </Button>
              </div>
              {webhooks.isLoading ? <SkeletonTable rows={3} /> : (
                <div className="space-y-2">
                  {webhookRows.length === 0 ? <p className="text-sm text-atlasly-muted">No webhooks configured</p> : null}
                  {webhookRows.map((webhook) => (
                    <div key={String(webhook.id ?? webhook.webhook_id)} className="flex items-center gap-3 rounded-md border border-atlasly-line px-4 py-3">
                      <div className="flex-1">
                        <p className="text-sm font-mono text-atlasly-ink truncate">{String(webhook.target_url ?? webhook.url ?? '—')}</p>
                        <p className="text-xs text-atlasly-muted mt-0.5">{formatDate(String(webhook.created_at ?? ''))}</p>
                      </div>
                      <Badge colorClass={webhook.is_active ? 'bg-atlasly-ok/20 text-atlasly-ok' : 'bg-gray-100 text-gray-500'}>
                        {webhook.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="api-keys" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>API Keys</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <div className="flex-1 space-y-1">
                  <Label htmlFor="key-name">Key Name</Label>
                  <Input id="key-name" value={keyName} onChange={(event) => setKeyName(event.target.value)} placeholder="CI/CD pipeline" autoComplete="off" />
                </div>
                <div className="flex items-end">
                  <Button onClick={() => createApiKey.mutate({ name: keyName }, { onSuccess: () => { setKeyName(''); apiKeys.refetch() } })} disabled={!keyName || createApiKey.isPending}>
                    {createApiKey.isPending ? 'Creating…' : 'Create'}
                  </Button>
                </div>
              </div>
              {apiKeys.isLoading ? <SkeletonTable rows={3} /> : (
                <div className="space-y-2">
                  {keyRows.length === 0 ? <p className="text-sm text-atlasly-muted">No API keys yet</p> : null}
                  {keyRows.map((key) => (
                    <div key={String(key.id ?? key.credential_id)} className="flex items-center gap-3 rounded-md border border-atlasly-line px-4 py-3">
                      <div className="flex-1">
                        <p className="text-sm font-medium text-atlasly-ink">{String(key.name ?? 'Unnamed key')}</p>
                        <p className="text-xs font-mono text-atlasly-muted mt-0.5">{String(key.fingerprint ?? key.key_prefix ?? key.id ?? '')}</p>
                      </div>
                      <p className="text-xs text-atlasly-muted">{formatDate(String(key.created_at ?? ''))}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="templates" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>Task Templates</CardTitle></CardHeader>
            <CardContent>
              {taskTemplates.isLoading ? <SkeletonTable rows={4} /> : (
                <div className="space-y-2">
                  {templateRows.length === 0 ? <p className="text-sm text-atlasly-muted">No task templates configured</p> : null}
                  {templateRows.map((template) => (
                    <div key={String(template.id ?? template.template_id)} className="rounded-md border border-atlasly-line px-4 py-3">
                      <p className="text-sm font-medium text-atlasly-ink">{String(template.name ?? 'Template')}</p>
                      <p className="text-xs text-atlasly-muted mt-0.5">{String(template.description ?? 'No description')}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>Audit Exports</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-atlasly-muted">Run the request → generate → complete audit export flow for compliance evidence.</p>
              <Button variant="outline" onClick={() => auditExport.mutate()} disabled={auditExport.isPending}>
                {auditExport.isPending ? 'Exporting…' : 'Export Audit Trail'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
