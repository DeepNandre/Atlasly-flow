import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface KpiCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  delta?: string
  deltaPositive?: boolean
  accent?: 'teal' | 'rust' | 'ok' | 'warn' | 'bad'
}

const accentMap = {
  teal: 'bg-atlasly-teal/10 text-atlasly-teal',
  rust: 'bg-atlasly-rust/10 text-atlasly-rust',
  ok: 'bg-atlasly-ok/10 text-atlasly-ok',
  warn: 'bg-atlasly-warn/10 text-atlasly-warn',
  bad: 'bg-atlasly-bad/10 text-atlasly-bad',
}

export function KpiCard({ label, value, icon: Icon, delta, deltaPositive, accent = 'teal' }: KpiCardProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-atlasly-muted uppercase tracking-wide">{label}</p>
            <p className="mt-1 text-2xl font-bold text-atlasly-ink">{value}</p>
            {delta && (
              <p className={cn('text-xs mt-1', deltaPositive ? 'text-atlasly-ok' : 'text-atlasly-bad')}>
                {delta}
              </p>
            )}
          </div>
          <div className={cn('rounded-lg p-2.5', accentMap[accent])}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
