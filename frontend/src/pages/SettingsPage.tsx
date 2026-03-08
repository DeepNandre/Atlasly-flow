import { useState } from 'react'
import { useWebhooks, useCreateWebhook, useApiKeys, useCreateApiKey, useAuditExport, useTaskTemplates } from '@/hooks/useApi'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { formatDate } from '@/lib/utils'

export default function SettingsPage() {
  const webhooks = useWebhooks()
  const createWebhook = useCreateWebhook()
  const apiKeys = useApiKeys()
  const createApiKey = useCreateApiKey()
  const auditExport = useAuditExport()
  const taskTemplates = useTaskTemplates()

  const [webhookUrl, setWebhookUrl] = useState('')
  const [keyName, setKeyName] = useState('')

  if (webhooks.error) return <ErrorState message="Could not load settings" onRetry={webhooks.refetch} />

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const whs: any[] = (webhooks.data as any)?.webhooks ?? []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const keys: any[] = (apiKeys.data as any)?.keys ?? []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const templates: any[] = (taskTemplates.data as any)?.templates ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Settings</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Manage webhooks, API keys, and exports</p>
      </div>

      <Tabs defaultValue="webhooks">
        <TabsList>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="api-keys">API Keys</TabsTrigger>
          <TabsTrigger value="templates">Task Templates</TabsTrigger>
          <TabsTrigger value="audit">Audit Exports</TabsTrigger>
        </TabsList>

        {/* Webhooks */}
        <TabsContent value="webhooks" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Webhook Subscriptions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <Input
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://your-server.com/webhook"
                  className="flex-1"
                />
                <Button
                  onClick={() => createWebhook.mutate({ url: webhookUrl }, { onSuccess: () => { setWebhookUrl(''); webhooks.refetch() } })}
                  disabled={!webhookUrl || createWebhook.isPending}
                >
                  {createWebhook.isPending ? 'Adding…' : 'Add'}
                </Button>
              </div>
              {webhooks.isLoading ? <SkeletonTable rows={3} /> : (
                <div className="space-y-2">
                  {whs.length === 0 && <p className="text-sm text-atlasly-muted">No webhooks configured</p>}
                  {whs.map((w) => (
                    <div key={w.webhook_id ?? w.id} className="flex items-center gap-3 rounded-md border border-atlasly-line px-4 py-3">
                      <div className="flex-1">
                        <p className="text-sm font-mono text-atlasly-ink truncate">{w.url}</p>
                        <p className="text-xs text-atlasly-muted mt-0.5">{formatDate(w.created_at)}</p>
                      </div>
                      <Badge colorClass={w.active ? 'bg-atlasly-ok/20 text-atlasly-ok' : 'bg-gray-100 text-gray-500'}>
                        {w.active ? 'Active' : 'Inactive'}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* API Keys */}
        <TabsContent value="api-keys" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>API Keys</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <div className="flex-1 space-y-1">
                  <Label htmlFor="key-name">Key Name</Label>
                  <Input id="key-name" value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="e.g. CI/CD pipeline" />
                </div>
                <div className="flex items-end">
                  <Button
                    onClick={() => createApiKey.mutate({ name: keyName }, { onSuccess: () => { setKeyName(''); apiKeys.refetch() } })}
                    disabled={!keyName || createApiKey.isPending}
                  >
                    {createApiKey.isPending ? 'Creating…' : 'Create'}
                  </Button>
                </div>
              </div>
              {apiKeys.isLoading ? <SkeletonTable rows={3} /> : (
                <div className="space-y-2">
                  {keys.length === 0 && <p className="text-sm text-atlasly-muted">No API keys yet</p>}
                  {keys.map((k) => (
                    <div key={k.key_id ?? k.id} className="flex items-center gap-3 rounded-md border border-atlasly-line px-4 py-3">
                      <div className="flex-1">
                        <p className="text-sm font-medium text-atlasly-ink">{k.name ?? 'Unnamed key'}</p>
                        <p className="text-xs font-mono text-atlasly-muted mt-0.5">{k.prefix ?? k.key_id}…</p>
                      </div>
                      <p className="text-xs text-atlasly-muted">{formatDate(k.created_at)}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Task templates */}
        <TabsContent value="templates" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>Task Templates</CardTitle></CardHeader>
            <CardContent>
              {taskTemplates.isLoading ? <SkeletonTable rows={4} /> : (
                <div className="space-y-2">
                  {templates.length === 0 && <p className="text-sm text-atlasly-muted">No task templates configured</p>}
                  {templates.map((t) => (
                    <div key={t.id ?? t.template_id} className="rounded-md border border-atlasly-line px-4 py-3">
                      <p className="text-sm font-medium text-atlasly-ink">{t.name ?? t.title ?? 'Template'}</p>
                      <p className="text-xs text-atlasly-muted mt-0.5">{t.discipline ?? ''} {t.description ?? ''}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Audit exports */}
        <TabsContent value="audit" className="space-y-4 mt-4">
          <Card>
            <CardHeader><CardTitle>Audit Exports</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-atlasly-muted">Export the full immutable audit trail for compliance reporting.</p>
              <Button
                variant="outline"
                onClick={() => auditExport.mutate({})}
                disabled={auditExport.isPending}
              >
                {auditExport.isPending ? 'Exporting…' : 'Export Audit Trail'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
