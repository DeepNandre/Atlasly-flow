import { useState } from 'react'
import { Bug, ChevronDown, ChevronUp } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { Role } from '@/lib/constants'

interface DemoToolbarProps {
  onRoleChange: (role: Role) => Promise<void>
  currentRole: Role
}

export function DemoToolbar({ onRoleChange, currentRole }: DemoToolbarProps) {
  const [open, setOpen] = useState(false)
  const [log, setLog] = useState<string[]>([])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try {
      const result = await fn()
      const entry = `[${new Date().toLocaleTimeString()}] ${label}: ${JSON.stringify(result).slice(0, 200)}`
      setLog((items) => [entry, ...items].slice(0, 50))
      toast.success(`${label} done`)
    } catch (error) {
      const entry = `[${new Date().toLocaleTimeString()}] ERROR ${label}: ${String(error)}`
      setLog((items) => [entry, ...items].slice(0, 50))
      toast.error(`${label} failed`)
    }
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-atlasly-rust bg-atlasly-slate text-white text-xs font-mono">
      <div className="flex items-center gap-2 px-4 py-2">
        <Bug className="h-3.5 w-3.5 text-atlasly-rust" />
        <span className="text-atlasly-rust font-semibold">DEMO</span>
        <div className="flex gap-2 flex-1 flex-wrap">
          <Button size="sm" variant="ghost" className="text-white h-7 text-xs" onClick={() => run('Bootstrap', () => api.post('/api/bootstrap', { org_name: 'Demo Org', user_name: 'owner', email: 'owner@demo.com' }))}>
            Bootstrap
          </Button>
          <Button size="sm" variant="ghost" className="text-white h-7 text-xs" onClick={() => run('Demo Scenario', () => api.post('/api/demo/run-scenario', {}))}>
            Run Demo
          </Button>
          <Button size="sm" variant="ghost" className="text-white h-7 text-xs" onClick={() => run('Reset', () => api.post('/api/demo/reset', {}))}>
            Reset
          </Button>
          <div className="w-36">
            <Select value={currentRole} onValueChange={(value) => { void onRoleChange(value as Role) }}>
              <SelectTrigger className="h-7 text-xs bg-atlasly-slate border-atlasly-line text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(['owner', 'admin', 'pm', 'reviewer', 'subcontractor'] as Role[]).map((role) => (
                  <SelectItem key={role} value={role}>{role}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <button type="button" onClick={() => setOpen((value) => !value)} className="ml-auto opacity-60 hover:opacity-100" aria-label="Toggle demo log">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
        </button>
      </div>
      {open ? (
        <div className="h-36 overflow-y-auto px-4 pb-2 space-y-0.5 border-t border-atlasly-line/30">
          {log.length === 0 ? <p className="text-atlasly-muted py-2">No log entries yet</p> : null}
          {log.map((entry, index) => (
            <p key={index} className="text-atlasly-line/80 leading-relaxed">{entry}</p>
          ))}
        </div>
      ) : null}
    </div>
  )
}
