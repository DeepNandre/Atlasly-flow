import { AlertTriangle, ArrowRight, Building2, CheckSquare, Plug, TrendingUp, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useActivity, usePortfolio, useReadiness, useStartDemoWorkspace, useSummary } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { ActivityFeed } from '@/components/shared/ActivityFeed'
import { ErrorState } from '@/components/shared/ErrorState'
import { KpiCard } from '@/components/shared/KpiCard'
import { SkeletonCard, SkeletonTable } from '@/components/shared/Skeleton'
import { PermitStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate } from '@/lib/utils'

export default function DashboardPage() {
  const portfolio = usePortfolio()
  const activity = useActivity()
  const summary = useSummary()
  const readiness = useReadiness()
  const startDemo = useStartDemoWorkspace()
  const { runtime } = useAuth()

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
  const bootstrapped = Boolean((summary.data as { bootstrapped?: boolean } | undefined)?.bootstrapped)
  const showGuidedDemo = !bootstrapped || projects.length === 0 || (counts.stage1a_letters ?? 0) === 0

  if (error) {
    return <ErrorState message="Could not load dashboard" onRetry={() => { portfolio.refetch(); summary.refetch(); activity.refetch() }} />
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Dashboard</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Overview of active projects, permits, and work queues</p>
      </div>

      {showGuidedDemo ? (
        <Card className="border-atlasly-teal/30 bg-[linear-gradient(135deg,#fffdf8_0%,#f1f7f4_100%)]">
          <CardContent className="p-5 md:p-6 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="space-y-3 max-w-2xl">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-atlasly-teal">Guided demo</p>
                <h2 className="text-lg font-semibold text-atlasly-ink mt-1">Show the permit workflow in under five minutes</h2>
              </div>
              <p className="text-sm text-atlasly-muted">
                Seed one project, one permit, one municipal comment letter, and one routed task flow. This gives a buyer a complete path from city comments to permit operations.
              </p>
              <div className="grid gap-2 text-sm text-atlasly-ink md:grid-cols-3">
                <div className="rounded-md border border-atlasly-line bg-white/80 px-3 py-2">1. Start demo workspace</div>
                <div className="rounded-md border border-atlasly-line bg-white/80 px-3 py-2">2. Review and approve the comment letter</div>
                <div className="rounded-md border border-atlasly-line bg-white/80 px-3 py-2">3. Open permits and integrations</div>
              </div>
              {(readiness.data as { warnings?: string[] } | undefined)?.warnings?.length ? (
                <div className="rounded-md border border-atlasly-warn/30 bg-atlasly-warn/10 px-3 py-2 text-xs text-atlasly-ink">
                  Runtime warnings: {((readiness.data as { warnings?: string[] }).warnings ?? []).join(', ')}
                </div>
              ) : null}
            </div>
            <div className="flex flex-col gap-2 md:w-56">
              <Button onClick={() => startDemo.mutate()} disabled={startDemo.isPending}>
                {startDemo.isPending ? 'Starting demo…' : 'Start Demo'}
              </Button>
              <Button asChild variant="outline">
                <Link to="/letters">
                  <UploadCloud className="mr-1.5 h-4 w-4" />
                  Upload your own letter
                </Link>
              </Button>
              <Button asChild variant="ghost">
                <Link to="/integrations">
                  <Plug className="mr-1.5 h-4 w-4" />
                  Connect city data
                </Link>
              </Button>
              <p className="text-xs text-atlasly-muted">
                Runtime: {runtime?.deployment_tier ?? 'unknown'} · {runtime?.runtime_backend ?? 'unknown backend'}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, index) => <SkeletonCard key={index} />)
        ) : (
          <>
            <KpiCard label="Active permits" value={kpis.permits_total ?? counts.stage0_permits ?? 0} icon={Building2} accent="teal" />
            <KpiCard label="Open tasks" value={kpis.tasks_open ?? counts.stage1b_tasks ?? 0} icon={CheckSquare} accent="warn" />
            <KpiCard label="Permits issued" value={kpis.permits_issued ?? 0} icon={TrendingUp} accent="ok" />
            <KpiCard label="Flagged items" value={flaggedItems} icon={AlertTriangle} accent="bad" />
          </>
        )}
      </div>

      {!loading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {[
            ['Cycle time', 'Use this to show how much permit drift and delay Atlasly can surface before it becomes a financing problem.'],
            ['Review queue', 'This tells operators where city status changes still need human confirmation.'],
            ['Connector health', 'This proves the product is not only parsing PDFs; it can maintain a live permit operations view.'],
            ['Task throughput', 'This shows how quickly comment letters become routed work instead of a buried PDF.'],
          ].map(([title, detail]) => (
            <div key={title} className="rounded-lg border border-atlasly-line bg-atlasly-paper px-4 py-3">
              <p className="text-sm font-medium text-atlasly-ink">{title}</p>
              <p className="mt-1 text-xs leading-5 text-atlasly-muted">{detail}</p>
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <CardTitle>Projects</CardTitle>
                <Link to="/permits" className="inline-flex items-center gap-1 text-xs font-medium text-atlasly-teal hover:underline">
                  Open permit ops
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
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
