import { useState } from 'react'
import { CheckSquare, ChevronDown, ChevronRight } from 'lucide-react'
import { useTasks, useRoutingAudit, useAssignTask } from '@/hooks/useApi'
import { TaskStatusBadge, DisciplineBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { formatDate } from '@/lib/utils'

export default function TasksPage() {
  const { data, isLoading, error, refetch } = useTasks()
  const audit = useRoutingAudit()
  const assign = useAssignTask()

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterDiscipline, setFilterDiscipline] = useState('all')
  const [auditOpen, setAuditOpen] = useState(false)
  const [assigneeInput, setAssigneeInput] = useState('')

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const allTasks: any[] = (data as any)?.tasks ?? (Array.isArray(data) ? data : [])

  const tasks = allTasks.filter((t) => {
    if (filterStatus !== 'all' && t.status !== filterStatus) return false
    if (filterDiscipline !== 'all' && t.discipline !== filterDiscipline) return false
    return true
  })

  const disciplines = [...new Set(allTasks.map((t) => t.discipline).filter(Boolean))]

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === tasks.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(tasks.map((t) => t.task_id ?? t.id)))
    }
  }

  const handleBulkAssign = () => {
    if (!assigneeInput.trim()) return
    selected.forEach((taskId) => {
      assign.mutate({ task_id: taskId, assignee_id: assigneeInput })
    })
    setSelected(new Set())
    setAssigneeInput('')
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const auditEntries: any[] = (audit.data as any)?.audit ?? (Array.isArray(audit.data) ? audit.data : [])

  if (error) return <ErrorState message="Could not load tasks" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-atlasly-ink">Tasks</h1>
        <p className="text-sm text-atlasly-muted mt-0.5">Action items extracted from comment letters</p>
      </div>

      {/* Bulk assign bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-atlasly-teal/40 bg-atlasly-teal/5 px-4 py-3">
          <span className="text-sm font-medium text-atlasly-teal">{selected.size} selected</span>
          <input
            value={assigneeInput}
            onChange={(e) => setAssigneeInput(e.target.value)}
            placeholder="Assignee ID or email"
            className="flex-1 max-w-xs h-8 rounded border border-atlasly-line bg-atlasly-paper px-3 text-sm focus:outline-none focus:ring-2 focus:ring-atlasly-teal"
          />
          <Button size="sm" onClick={handleBulkAssign} disabled={!assigneeInput.trim() || assign.isPending}>
            Assign Selected
          </Button>
          <button onClick={() => setSelected(new Set())} className="text-xs text-atlasly-muted hover:text-atlasly-ink">
            Cancel
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-40 h-8 text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="escalated">Escalated</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterDiscipline} onValueChange={setFilterDiscipline}>
          <SelectTrigger className="w-40 h-8 text-xs">
            <SelectValue placeholder="All disciplines" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All disciplines</SelectItem>
            {disciplines.map((d) => (
              <SelectItem key={d} value={d}>{d}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={6} /></div>
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={CheckSquare}
              title="No tasks yet"
              description="Tasks are created when you approve a comment letter"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-atlasly-line">
                    <th className="px-5 py-3 w-10">
                      <Checkbox
                        checked={selected.size === tasks.length && tasks.length > 0}
                        onCheckedChange={toggleAll}
                      />
                    </th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Task</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Discipline</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Assignee</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Due</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => {
                    const id = t.task_id ?? t.id
                    return (
                      <tr key={id} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40">
                        <td className="px-5 py-3">
                          <Checkbox
                            checked={selected.has(id)}
                            onCheckedChange={() => toggleSelect(id)}
                          />
                        </td>
                        <td className="px-4 py-3 font-medium text-atlasly-ink max-w-xs truncate">
                          {t.title ?? t.description ?? t.action_needed ?? 'Task'}
                        </td>
                        <td className="px-4 py-3">
                          {t.discipline ? <DisciplineBadge discipline={t.discipline} /> : '—'}
                        </td>
                        <td className="px-4 py-3 text-atlasly-muted">{t.assignee_name ?? t.assignee_id ?? 'Unassigned'}</td>
                        <td className="px-4 py-3 text-atlasly-muted">{formatDate(t.due_date)}</td>
                        <td className="px-4 py-3">
                          <TaskStatusBadge status={t.status ?? 'open'} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Routing audit */}
      <Collapsible open={auditOpen} onOpenChange={setAuditOpen}>
        <CollapsibleTrigger asChild>
          <button className="flex items-center gap-2 text-sm font-medium text-atlasly-muted hover:text-atlasly-ink">
            {auditOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            Routing Audit
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <Card className="mt-3">
            <CardHeader>
              <CardTitle>Auto-Routing Log</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {audit.isLoading ? (
                <div className="p-5"><SkeletonTable rows={4} /></div>
              ) : auditEntries.length === 0 ? (
                <p className="text-sm text-atlasly-muted p-5">No routing events yet</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-atlasly-line">
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Task</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Routed To</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Rule</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEntries.map((a, i) => (
                      <tr key={i} className="border-b border-atlasly-line last:border-0">
                        <td className="px-5 py-2.5 text-atlasly-ink">{a.task_id ?? '—'}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted">{a.assignee_id ?? a.routed_to ?? '—'}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted text-xs font-mono">{a.rule ?? a.routing_rule ?? '—'}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted">{formatDate(a.assigned_at ?? a.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
