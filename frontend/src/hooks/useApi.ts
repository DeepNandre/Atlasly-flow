import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError } from '@/lib/api'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message
  }
  return 'Unexpected error'
}

function toastError(prefix: string, error: unknown) {
  toast.error(`${prefix}: ${errorMessage(error)}`)
}

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.get('/api/portfolio'),
    retry: 1,
  })
}

export function useActivity() {
  return useQuery({
    queryKey: ['activity'],
    queryFn: () => api.get('/api/activity'),
    retry: 1,
  })
}

export function useSummary() {
  return useQuery({
    queryKey: ['summary'],
    queryFn: () => api.get('/api/summary'),
    retry: 1,
  })
}

export function useCommentLetters() {
  return useQuery({
    queryKey: ['letters'],
    queryFn: () => api.get('/api/stage1a/letters'),
    retry: 1,
  })
}

export function useLetterExtractions(letterId?: string) {
  return useQuery({
    queryKey: ['letter-extractions', letterId],
    queryFn: () => api.get(`/api/stage1a/extractions?letter_id=${letterId}`),
    enabled: Boolean(letterId),
    retry: 1,
  })
}

export function useQualityReport() {
  return useQuery({
    queryKey: ['quality-report'],
    queryFn: () => api.get('/api/stage1a/quality-report'),
    retry: 1,
  })
}

export function useUploadLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { filename: string; mime_type: string; document_base64: string }) =>
      api.post('/api/stage1a/upload', { ...body, auto_process: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      toast.success('Comment letter uploaded')
    },
    onError: (error: unknown) => toastError('Upload failed', error),
  })
}

export function useParseComments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { text?: string; filename?: string; mime_type?: string; document_base64?: string }) =>
      api.post('/api/stage1a/parse', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      toast.success('Comment letter parsed successfully')
    },
    onError: (error: unknown) => toastError('Parse failed', error),
  })
}

export function useReviewExtraction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { letter_id: string; extraction_id: string; action: 'accept' | 'reject' }) =>
      api.post('/api/stage1a/review', body),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      qc.invalidateQueries({ queryKey: ['letter-extractions', variables.letter_id] })
      toast.success('Extraction reviewed')
    },
    onError: (error: unknown) => toastError('Review failed', error),
  })
}

export function useApproveAndCreateTasks() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { letter_id: string }) =>
      api.post('/api/stage1a/approve-and-create-tasks', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Letter approved and tasks created')
    },
    onError: (error: unknown) => toastError('Approval failed', error),
  })
}

export function useTasks() {
  return useQuery({
    queryKey: ['tasks'],
    queryFn: () => api.get('/api/stage1b/tasks'),
    retry: 1,
  })
}

export function useRoutingAudit() {
  return useQuery({
    queryKey: ['routing-audit'],
    queryFn: () => api.get('/api/stage1b/routing-audit'),
    retry: 1,
  })
}

export function useAssignTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { task_id: string; assignee_id: string }) => api.post('/api/stage1b/assign', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['routing-audit'] })
      toast.success('Task assignment updated')
    },
    onError: (error: unknown) => toastError('Assignment failed', error),
  })
}

export function useEscalationTick() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: { user_mode?: 'immediate' | 'digest' }) => api.post('/api/stage1b/escalation-tick', body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['routing-audit'] })
      toast.success('Escalation worker run complete')
    },
    onError: (error: unknown) => toastError('Escalation run failed', error),
  })
}

export function usePermits() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => api.get('/api/portfolio'),
    retry: 1,
  })
}

export function usePermitOps() {
  return useQuery({
    queryKey: ['permit-ops'],
    queryFn: () => api.get('/api/permit-ops'),
    retry: 1,
  })
}

export function usePermitTimeline(permitId: string) {
  return useQuery({
    queryKey: ['permit-timeline', permitId],
    queryFn: () => api.get(`/api/stage2/timeline?permit_id=${permitId}`),
    enabled: Boolean(permitId),
    retry: 1,
  })
}

export function useIntakeComplete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post('/api/stage2/intake-complete', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] })
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      toast.success('Permit intake submitted')
    },
    onError: (error: unknown) => toastError('Intake failed', error),
  })
}

export function useResolveAhj() {
  return useMutation({
    mutationFn: (body: { address: { line1: string; city: string; state: string; postal_code: string } }) =>
      api.post('/api/stage2/resolve-ahj', body),
    onError: (error: unknown) => toastError('AHJ lookup failed', error),
  })
}

export function usePollPermitStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body?: { raw_status?: string }) => api.post('/api/stage2/poll-status', body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] })
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      qc.invalidateQueries({ queryKey: ['permit-timeline'] })
      toast.success('Status sync complete')
    },
    onError: (error: unknown) => toastError('Sync failed', error),
  })
}

export function usePollLiveConnector() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { connector: string; ahj_id: string; credential_ref?: string }) =>
      api.post('/api/stage2/poll-live', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio'] })
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      qc.invalidateQueries({ queryKey: ['permit-timeline'] })
      qc.invalidateQueries({ queryKey: ['integrations-readiness'] })
      qc.invalidateQueries({ queryKey: ['launch-readiness'] })
      toast.success('Live connector poll completed')
    },
    onError: (error: unknown) => toastError('Live connector poll failed', error),
  })
}

export function useResolveTransition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { review_id: string; resolution_state: 'open' | 'resolved' | 'dismissed' }) =>
      api.post('/api/permit-ops/resolve-transition', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      toast.success('Transition review updated')
    },
    onError: (error: unknown) => toastError('Transition update failed', error),
  })
}

export function useResolveDrift() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { alert_id: string; status: 'open' | 'resolved' | 'dismissed' }) =>
      api.post('/api/permit-ops/resolve-drift', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      toast.success('Drift alert updated')
    },
    onError: (error: unknown) => toastError('Drift resolution failed', error),
  })
}

export function useFinanceOps() {
  return useQuery({
    queryKey: ['finance-ops'],
    queryFn: () => api.get('/api/finance-ops'),
    retry: 1,
  })
}

export function usePayoutPreflight() {
  return useMutation({
    mutationFn: () => api.post('/api/stage3/preflight', {}),
    onError: (error: unknown) => toastError('Preflight failed', error),
  })
}

export function useCreatePayout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { amount: number; beneficiary_id: string; provider?: string }) =>
      api.post('/api/stage3/payout', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['finance-ops'] })
      qc.invalidateQueries({ queryKey: ['payout-outbox'] })
      toast.success('Payout instruction created')
    },
    onError: (error: unknown) => toastError('Payout failed', error),
  })
}

export function useReconcile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/stage3/reconcile', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['finance-ops'] })
      toast.success('Reconciliation complete')
    },
    onError: (error: unknown) => toastError('Reconciliation failed', error),
  })
}

export function usePayoutOutbox() {
  return useQuery({
    queryKey: ['payout-outbox'],
    queryFn: () => api.get('/api/stage3/outbox'),
    retry: 1,
  })
}

export function usePublishOutbox() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/api/stage3/publish-outbox', {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payout-outbox'] })
      qc.invalidateQueries({ queryKey: ['finance-ops'] })
      toast.success('Outbox published')
    },
    onError: (error: unknown) => toastError('Publish failed', error),
  })
}

export function useIntegrationsReadiness() {
  return useQuery({
    queryKey: ['integrations-readiness'],
    queryFn: () => api.get('/api/enterprise/integrations-readiness'),
    retry: 1,
  })
}

export function useLaunchReadiness() {
  return useQuery({
    queryKey: ['launch-readiness'],
    queryFn: () => api.get('/api/enterprise/launch-readiness'),
    retry: 1,
  })
}

export function useSlo() {
  return useQuery({
    queryKey: ['slo'],
    queryFn: () => api.get('/api/enterprise/slo'),
    retry: 1,
  })
}

export function useConnectorSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { connector_name: string; run_mode?: string }) => api.post('/api/enterprise/connector-sync', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations-readiness'] })
      toast.success('Connector sync started')
    },
    onError: (error: unknown) => toastError('Sync failed', error),
  })
}

export function useRotateCredentials() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { connector: string; credential_ref: string; auth_scheme?: string }) =>
      api.post('/api/stage2/connector-credentials/rotate', { ...body, auth_scheme: body.auth_scheme ?? 'bearer' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations-readiness'] })
      qc.invalidateQueries({ queryKey: ['connector-credentials'] })
      toast.success('Credential reference rotated')
    },
    onError: (error: unknown) => toastError('Rotation failed', error),
  })
}

export function useConnectorCredentials(connector?: string) {
  const suffix = connector ? `?connector=${connector}` : ''
  return useQuery({
    queryKey: ['connector-credentials', connector],
    queryFn: () => api.get(`/api/stage2/connector-credentials${suffix}`),
    retry: 1,
  })
}

export function usePermitBindings(connector?: string, ahjId?: string) {
  const params = new URLSearchParams()
  if (connector) params.set('connector', connector)
  if (ahjId) params.set('ahj_id', ahjId)
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  return useQuery({
    queryKey: ['permit-bindings', connector, ahjId],
    queryFn: () => api.get(`/api/stage2/permit-bindings${suffix}`),
    retry: 1,
  })
}

export function useCreatePermitBinding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { connector: string; ahj_id: string; permit_id: string; external_permit_id: string; external_record_ref?: string }) =>
      api.post('/api/stage2/permit-bindings', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permit-bindings'] })
      qc.invalidateQueries({ queryKey: ['permit-ops'] })
      toast.success('Permit binding saved')
    },
    onError: (error: unknown) => toastError('Binding failed', error),
  })
}

export function useWebhooks() {
  return useQuery({
    queryKey: ['webhooks'],
    queryFn: () => api.get('/api/enterprise/webhooks'),
    retry: 1,
  })
}

export function useCreateWebhook() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { target_url: string }) => api.post('/api/enterprise/webhooks', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks'] })
      toast.success('Webhook created')
    },
    onError: (error: unknown) => toastError('Webhook creation failed', error),
  })
}

export function useApiKeys() {
  return useQuery({
    queryKey: ['api-keys'],
    queryFn: () => api.get('/api/enterprise/api-keys'),
    retry: 1,
  })
}

export function useCreateApiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string }) =>
      api.post('/api/enterprise/api-keys', {
        name: body.name,
        scopes: ['dashboard:read', 'webhooks:read'],
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success('API key created')
    },
    onError: (error: unknown) => toastError('Key creation failed', error),
  })
}

export function useAuditExport() {
  return useMutation({
    mutationFn: async () => {
      const requested = await api.post<{ export_id: string }>('/api/enterprise/audit-exports/request', {})
      await api.post('/api/enterprise/audit-exports/run', { export_id: requested.export_id })
      return api.post('/api/enterprise/audit-exports/complete', {
        export_id: requested.export_id,
        checksum: 'sha256:atlasly-control-tower',
        storage_uri: `local://audit-exports/${requested.export_id}.json`,
        access_log_ref: `audit-log-${requested.export_id}`,
      })
    },
    onSuccess: () => toast.success('Audit export completed'),
    onError: (error: unknown) => toastError('Audit export failed', error),
  })
}

export function useDashboardSnapshot() {
  return useMutation({
    mutationFn: () => api.post('/api/enterprise/dashboard-snapshot', {}),
    onSuccess: () => toast.success('Snapshot created'),
    onError: (error: unknown) => toastError('Snapshot failed', error),
  })
}

export function useTaskTemplates() {
  return useQuery({
    queryKey: ['task-templates'],
    queryFn: () => api.get('/api/enterprise/task-templates'),
    retry: 1,
  })
}
