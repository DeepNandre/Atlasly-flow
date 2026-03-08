import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'

// ─── Dashboard ───────────────────────────────────────────────────────────────

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

// ─── Comment Letters ─────────────────────────────────────────────────────────

export function useCommentLetters() {
  return useQuery({
    queryKey: ['letters'],
    queryFn: () => api.get('/api/stage1a/letters'),
    retry: 1,
  })
}

export function useQualityReport(letterId?: string) {
  return useQuery({
    queryKey: ['quality-report', letterId],
    queryFn: () => api.get(`/api/stage1a/quality-report${letterId ? `?letter_id=${letterId}` : ''}`),
    enabled: !!letterId,
    retry: 1,
  })
}

export function useUploadLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { filename: string; content_b64: string }) =>
      api.post('/api/stage1a/upload', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      toast.success('Comment letter uploaded — extraction started')
    },
    onError: (e: Error) => toast.error(`Upload failed: ${e.message}`),
  })
}

export function useParseComments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { raw_text?: string; filename?: string }) =>
      api.post('/api/stage1a/parse', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      toast.success('Comment letter parsed successfully')
    },
    onError: (e: Error) => toast.error(`Parse failed: ${e.message}`),
  })
}

export function useReviewExtraction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { letter_id: string; extraction_id: string; action: string; note?: string }) =>
      api.post('/api/stage1a/review', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['letters'] })
      toast.success('Extraction reviewed')
    },
    onError: (e: Error) => toast.error(`Review failed: ${e.message}`),
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
      toast.success('Letter approved — tasks created and routed')
    },
    onError: (e: Error) => toast.error(`Approval failed: ${e.message}`),
  })
}

// ─── Tasks ────────────────────────────────────────────────────────────────────

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
    mutationFn: (body: { task_id: string; assignee_id: string }) =>
      api.post('/api/stage1b/assign', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task assigned')
    },
    onError: (e: Error) => toast.error(`Assignment failed: ${e.message}`),
  })
}

// ─── Permits ──────────────────────────────────────────────────────────────────

export function usePermits() {
  return useQuery({
    queryKey: ['permits'],
    queryFn: () => api.get('/api/permit-ops'),
    retry: 1,
  })
}

export function usePermitTimeline(permitId: string) {
  return useQuery({
    queryKey: ['permit-timeline', permitId],
    queryFn: () => api.get(`/api/stage2/timeline?permit_id=${permitId}`),
    enabled: !!permitId,
    retry: 1,
  })
}

export function useIntakeComplete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/stage2/intake-complete', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permits'] })
      toast.success('Permit intake submitted')
    },
    onError: (e: Error) => toast.error(`Intake failed: ${e.message}`),
  })
}

export function useResolveAhj() {
  return useMutation({
    mutationFn: (body: { address: string }) =>
      api.post('/api/stage2/resolve-ahj', body),
    onError: (e: Error) => toast.error(`AHJ lookup failed: ${e.message}`),
  })
}

export function usePollPermitStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { permit_id: string }) =>
      api.post('/api/stage2/poll-status', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permits'] })
      toast.success('Status synced with city')
    },
    onError: (e: Error) => toast.error(`Sync failed: ${e.message}`),
  })
}

export function useResolveDrift() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { permit_id: string; resolution: string }) =>
      api.post('/api/permit-ops/resolve-drift', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['permits'] })
      toast.success('Drift resolved')
    },
    onError: (e: Error) => toast.error(`Resolution failed: ${e.message}`),
  })
}

// ─── Payouts ──────────────────────────────────────────────────────────────────

export function useFinanceOps() {
  return useQuery({
    queryKey: ['finance-ops'],
    queryFn: () => api.get('/api/finance-ops'),
    retry: 1,
  })
}

export function usePayoutPreflight() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/stage3/preflight', body),
    onError: (e: Error) => toast.error(`Preflight failed: ${e.message}`),
  })
}

export function useCreatePayout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/stage3/payout', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['finance-ops'] })
      toast.success('Payout instruction created')
    },
    onError: (e: Error) => toast.error(`Payout failed: ${e.message}`),
  })
}

export function useReconcile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/stage3/reconcile', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['finance-ops'] })
      toast.success('Reconciliation complete')
    },
    onError: (e: Error) => toast.error(`Reconciliation failed: ${e.message}`),
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
    mutationFn: () => api.post('/api/stage3/publish-outbox'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payout-outbox'] })
      toast.success('Outbox published')
    },
    onError: (e: Error) => toast.error(`Publish failed: ${e.message}`),
  })
}

// ─── Integrations ─────────────────────────────────────────────────────────────

export function useIntegrationsReadiness() {
  return useQuery({
    queryKey: ['integrations-readiness'],
    queryFn: () => api.get('/api/enterprise/integrations-readiness'),
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
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/enterprise/connector-sync', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations-readiness'] })
      toast.success('Connector sync started')
    },
    onError: (e: Error) => toast.error(`Sync failed: ${e.message}`),
  })
}

export function useRotateCredentials() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { connector: string; credential: string }) =>
      api.post('/api/stage2/connector-credentials/rotate', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations-readiness'] })
      toast.success('Credentials rotated')
    },
    onError: (e: Error) => toast.error(`Rotation failed: ${e.message}`),
  })
}

// ─── Settings ─────────────────────────────────────────────────────────────────

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
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/enterprise/webhooks', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks'] })
      toast.success('Webhook created')
    },
    onError: (e: Error) => toast.error(`Webhook creation failed: ${e.message}`),
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
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/enterprise/api-keys', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success('API key created')
    },
    onError: (e: Error) => toast.error(`Key creation failed: ${e.message}`),
  })
}

export function useAuditExport() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post('/api/enterprise/audit-export', body),
    onSuccess: () => toast.success('Audit export started — check your email'),
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  })
}

export function useDashboardSnapshot() {
  return useMutation({
    mutationFn: () => api.post('/api/enterprise/dashboard-snapshot'),
    onSuccess: () => toast.success('Snapshot created'),
    onError: (e: Error) => toast.error(`Snapshot failed: ${e.message}`),
  })
}

export function useTaskTemplates() {
  return useQuery({
    queryKey: ['task-templates'],
    queryFn: () => api.get('/api/enterprise/task-templates'),
    retry: 1,
  })
}
