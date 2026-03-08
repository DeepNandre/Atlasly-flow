import { formatRelative } from '@/lib/utils'
import { ACTIVITY_LABELS } from '@/lib/constants'

interface ActivityEvent {
  event_type?: string
  event_name?: string
  summary?: string
  created_at?: string
  occurred_at?: string
  meta?: Record<string, unknown>
}

interface ActivityFeedProps {
  events: ActivityEvent[]
  maxItems?: number
}

export function ActivityFeed({ events, maxItems = 20 }: ActivityFeedProps) {
  const items = events.slice(0, maxItems)

  return (
    <ol className="space-y-3">
      {items.map((ev, i) => {
        const type = ev.event_type ?? ev.event_name ?? 'event'
        const label = ev.summary ?? ACTIVITY_LABELS[type] ?? type.replace(/_/g, ' ').replace(/\./g, ' › ')
        const time = ev.created_at ?? ev.occurred_at
        return (
          <li key={i} className="flex items-start gap-3">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-atlasly-teal" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-atlasly-ink leading-snug">{label}</p>
              <p className="text-xs text-atlasly-muted mt-0.5">{formatRelative(time)}</p>
            </div>
          </li>
        )
      })}
      {items.length === 0 && (
        <li className="text-sm text-atlasly-muted py-4 text-center">No recent activity</li>
      )}
    </ol>
  )
}
