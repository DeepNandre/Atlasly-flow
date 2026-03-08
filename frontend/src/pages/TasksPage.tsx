import { useMemo, useState } from 'react'
import { CheckSquare, ChevronDown, ChevronRight, TimerReset } from 'lucide-react'
import { useAssignTask, useEscalationTick, useRoutingAudit, useTasks } from '@/hooks/useApi'
import { DisciplineBadge, TaskStatusBadge } from '@/components/shared/StatusBadge'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatDate } from '@/lib/utils'

export default function TasksPage() {
  const { data, isLoading, error, refetch } = useTasks()
  const audit = useRoutingAudit()
  const assign = useAssignTask()
  const escalation = useEscalationTick()

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterDiscipline, setFilterDiscipline] = useState('all')
  const [auditOpen, setAuditOpen] = useState(false)
  const [assigneeInput, setAssigneeInput] = useState('')

  const tasks = useMemo(() => {
    const allTasks = ((data as { tasks?: Array<Record<string, unknown>> } | undefined)?.tasks ?? [])
    return allTasks.filter((task) => {
      const status = String(task.status ?? 'open')
      const discipline = String(task.discipline ?? '')
      if (filterStatus !== 'all' && status !== filterStatus) return false
      if (filterDiscipline !== 'all' && discipline !== filterDiscipline) return false
      return true
    })
  }, [data, filterDiscipline, filterStatus])
  const disciplines = useMemo(() => {
    const allTasks = ((data as { tasks?: Array<Record<string, unknown>> } | undefined)?.tasks ?? [])
    return [...new Set(allTasks.map((task) => String(task.discipline ?? '')).filter(Boolean))]
  }, [data])
  const auditEntries = ((audit.data as { items?: Array<Record<string, unknown>> } | undefined)?.items ?? [])

  if (error) return <ErrorState message="Could not load tasks" onRetry={refetch} />

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleBulkAssign = () => {
    const assigneeId = assigneeInput.trim()
    if (!assigneeId) return
    selected.forEach((taskId) => assign.mutate({ task_id: taskId, assignee_id: assigneeId }))
    setSelected(new Set())
    setAssigneeInput('')
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Tasks</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Action items extracted from comment letters</p>
        </div>
        <Button variant="outline" onClick={() => escalation.mutate({ user_mode: 'immediate' })} disabled={escalation.isPending}>
          <TimerReset className="h-4 w-4 mr-1" />
          {escalation.isPending ? 'Running…' : 'Run Escalation Check'}
        </Button>
      </div>

      {selected.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-atlasly-teal/40 bg-atlasly-teal/5 px-4 py-3 flex-wrap">
          <span className="text-sm font-medium text-atlasly-teal">{selected.size} selected</span>
          <Input
            value={assigneeInput}
            onChange={(event) => setAssigneeInput(event.target.value)}
            placeholder="Assignee ID"
            className="flex-1 max-w-xs"
            autoComplete="off"
          />
          <Button size="sm" onClick={handleBulkAssign} disabled={!assigneeInput.trim() || assign.isPending}>
            Assign Selected
          </Button>
          <button type="button" onClick={() => setSelected(new Set())} className="text-xs text-atlasly-muted hover:text-atlasly-ink">
            Cancel
          </button>
        </div>
      )}

      <div className="flex gap-3 flex-wrap">
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-40 h-8 text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="blocked">Blocked</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterDiscipline} onValueChange={setFilterDiscipline}>
          <SelectTrigger className="w-44 h-8 text-xs">
            <SelectValue placeholder="All disciplines" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All disciplines</SelectItem>
            {disciplines.map((discipline) => (
              <SelectItem key={discipline} value={discipline}>{discipline}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={6} /></div>
          ) : tasks.length === 0 ? (
            <EmptyState icon={CheckSquare} title="No tasks yet" description="Approve a comment letter to create routed tasks." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-atlasly-line">
                    <th className="px-5 py-3 w-10">
                      <Checkbox
                        checked={selected.size === tasks.length && tasks.length > 0}
                        onCheckedChange={() => setSelected(selected.size === tasks.length ? new Set() : new Set(tasks.map((task) => String(task.id ?? task.task_id))))}
                      />
                    </th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Task</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Discipline</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Routing</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Assignee</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => {
                    const id = String(task.id ?? task.task_id)
                    return (
                      <tr key={id} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40">
                        <td className="px-5 py-3">
                          <Checkbox checked={selected.has(id)} onCheckedChange={() => toggleSelect(id)} />
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-atlasly-ink max-w-sm truncate">{String(task.title ?? task.description ?? 'Task')}</div>
                          <div className="text-xs text-atlasly-muted mt-1">Created {formatDate(String(task.created_at ?? ''))}</div>
                        </td>
                        <td className="px-4 py-3">{task.discipline ? <DisciplineBadge discipline={String(task.discipline)} /> : '—'}</td>
                        <td className="px-4 py-3 text-atlasly-muted">
                          <div>{String(task.routing_decision ?? task.routing_reason ?? 'manual')}</div>
                          <div className="text-xs">{String(task.routing_rule_id ?? task.routing_reason ?? '')}</div>
                        </td>
                        <td className="px-4 py-3 text-atlasly-muted">{String(task.assignee_user_id ?? 'Unassigned')}</td>
                        <td className="px-4 py-3"><TaskStatusBadge status={String(task.status ?? 'open')} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Collapsible open={auditOpen} onOpenChange={setAuditOpen}>
        <CollapsibleTrigger asChild>
          <button type="button" className="flex items-center gap-2 text-sm font-medium text-atlasly-muted hover:text-atlasly-ink">
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
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Decision</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Rule</th>
                      <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditEntries.map((entry) => (
                      <tr key={String(entry.task_id)} className="border-b border-atlasly-line last:border-0">
                        <td className="px-5 py-2.5 text-atlasly-ink">{String(entry.task_id ?? '—')}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted">{String(entry.routing_reason ?? entry.manual_queue_reason ?? '—')}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted text-xs font-mono">{String(entry.routing_rule_id ?? '—')}</td>
                        <td className="px-5 py-2.5 text-atlasly-muted">{formatDate(String(entry.updated_at ?? ''))}</td>
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
