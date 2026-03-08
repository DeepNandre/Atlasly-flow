import { Building2, CheckSquare, AlertTriangle, TrendingUp } from 'lucide-react'
import { usePortfolio, useActivity, useSummary } from '@/hooks/useApi'
import { KpiCard } from '@/components/shared/KpiCard'
import { ActivityFeed } from '@/components/shared/ActivityFeed'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonCard, SkeletonTable } from '@/components/shared/Skeleton'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { formatDate } from '@/lib/utils'

export default function DashboardPage() {
  const portfolio = usePortfolio()
  const activity = useActivity()
  const summary = useSummary()

  const loading = portfolio.isLoading || summary.isLoading
  const error = portfolio.error ?? summary.error

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = (portfolio.data as any) ?? {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sum = (summary.data as any) ?? {}
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const acts: any[] = (activity.data as any)?.events ?? []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const projects: any[] = data.projects ?? []

  if (error) {
    return <ErrorState message="Could not load dashboard" onRetry={() => { portfolio.refetch(); summary.refetch() }} />
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Dashboard</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Overview of your active projects and permits</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : (
          <>
            <KpiCard label="Active Permits" value={sum.active_permits ?? data.active_permits ?? '—'} icon={Building2} accent="teal" />
            <KpiCard label="Open Tasks" value={sum.open_tasks ?? '—'} icon={CheckSquare} accent="warn" />
            <KpiCard label="Permits Issued" value={sum.permits_issued ?? '—'} icon={TrendingUp} accent="ok" />
            <KpiCard label="Flagged Items" value={sum.flagged ?? sum.needs_attention ?? '—'} icon={AlertTriangle} accent="bad" />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Projects table */}
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
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                        <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Updated</th>
                      </tr>
                    </thead>
                    <tbody>
                      {projects.map((p, i) => (
                        <tr key={p.project_id ?? i} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50">
                          <td className="px-5 py-3 font-medium text-atlasly-ink">{p.name ?? p.project_name ?? 'Unnamed project'}</td>
                          <td className="px-5 py-3 text-atlasly-muted">{p.permit_count ?? '—'}</td>
                          <td className="px-5 py-3">
                            {p.status ? <PermitStatusBadge status={p.status} /> : <span className="text-atlasly-muted">—</span>}
                          </td>
                          <td className="px-5 py-3 text-atlasly-muted">{formatDate(p.updated_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Activity feed */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {activity.isLoading ? (
              <SkeletonTable rows={6} />
            ) : (
              <ActivityFeed events={acts} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
