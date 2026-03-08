import { AlertTriangle, Building2, CheckSquare, TrendingUp } from 'lucide-react'
import { useActivity, usePortfolio, useSummary } from '@/hooks/useApi'
import { ActivityFeed } from '@/components/shared/ActivityFeed'
import { ErrorState } from '@/components/shared/ErrorState'
import { KpiCard } from '@/components/shared/KpiCard'
import { SkeletonCard, SkeletonTable } from '@/components/shared/Skeleton'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/utils'

export default function DashboardPage() {
  const portfolio = usePortfolio()
  const activity = useActivity()
  const summary = useSummary()

  const loading = portfolio.isLoading || summary.isLoading
  const error = portfolio.error ?? summary.error ?? activity.error

  const portfolioData = (portfolio.data as {
    kpis?: Record<string, number>
    projects?: Array<Record<string, unknown>>
  } | undefined) ?? {}
  const summaryData = (summary.data as { counts?: Record<string, number> } | undefined) ?? {}
  const activityData = (activity.data as { events?: Array<Record<string, unknown>> } | undefined) ?? {}

  const projects = portfolioData.projects ?? []
  const counts = summaryData.counts ?? {}
  const kpis = portfolioData.kpis ?? {}
  const flaggedItems = (counts.stage1b_manual_queue ?? 0) + (counts.stage1a_letters ?? 0 > 0 ? 1 : 0)

  if (error) {
    return <ErrorState message="Could not load dashboard" onRetry={() => { portfolio.refetch(); summary.refetch(); activity.refetch() }} />
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Dashboard</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Overview of active projects, permits, and work queues</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, index) => <SkeletonCard key={index} />)
        ) : (
          <>
            <KpiCard label="Active Permits" value={kpis.permits_total ?? counts.stage0_permits ?? 0} icon={Building2} accent="teal" />
            <KpiCard label="Open Tasks" value={kpis.tasks_open ?? counts.stage1b_tasks ?? 0} icon={CheckSquare} accent="warn" />
            <KpiCard label="Permits Issued" value={kpis.permits_issued ?? 0} icon={TrendingUp} accent="ok" />
            <KpiCard label="Flagged Items" value={flaggedItems} icon={AlertTriangle} accent="bad" />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Projects</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="p-5"><SkeletonTable rows={4} /></div>
              ) : projects.length === 0 ? (
                <p className="text-sm text-atlasly-muted p-5">No projects yet</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-atlasly-line">
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Project</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Permits</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Risk</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projects.map((project) => {
                        const record = project as {
                          project_id?: string
                          name?: string
                          permit_count?: number
                          risk_level?: string
                          permits?: Array<{ status?: string; updated_at?: string }>
                        }
                        const latestPermit = record.permits?.[0]
                        return (
                          <tr key={record.project_id ?? record.name} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50">
                            <td className="px-5 py-3 font-medium text-atlasly-ink">{record.name ?? 'Unnamed project'}</td>
                            <td className="px-5 py-3 text-atlasly-muted">{record.permit_count ?? 0}</td>
                            <td className="px-5 py-3">
                              {latestPermit?.status ? <PermitStatusBadge status={latestPermit.status} /> : <span className="text-atlasly-muted">{record.risk_level ?? '—'}</span>}
                            </td>
                            <td className="px-5 py-3 text-atlasly-muted">{formatDate(latestPermit?.updated_at)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {activity.isLoading ? <SkeletonTable rows={6} /> : <ActivityFeed events={activityData.events ?? []} />}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
