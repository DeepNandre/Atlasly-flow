import { CheckCircle, Circle, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/utils'

const TIMELINE_STEPS = [
  { key: 'draft', label: 'Draft' },
  { key: 'submitted', label: 'Submitted' },
  { key: 'in_review', label: 'In Review' },
  { key: 'approved', label: 'Approved' },
  { key: 'issued', label: 'Issued' },
]

const ORDER = TIMELINE_STEPS.map((s) => s.key)

interface TimelineEvent {
  status?: string
  normalized_status?: string
  occurred_at?: string
  observed_at?: string
  created_at?: string
  note?: string
}

interface StatusTimelineProps {
  currentStatus?: string
  events?: TimelineEvent[]
}

export function StatusTimeline({ currentStatus, events = [] }: StatusTimelineProps) {
  const currentIndex = ORDER.indexOf(currentStatus ?? 'draft')

  return (
    <div className="flex items-start gap-0 overflow-x-auto py-2">
      {TIMELINE_STEPS.map((step, i) => {
        const done = i < currentIndex
        const active = i === currentIndex
        const event = events.find((e) => (e.normalized_status ?? e.status) === step.key)

        return (
          <div key={step.key} className="flex items-start flex-1 min-w-0">
            <div className="flex flex-col items-center">
              <div className={cn(
                'h-8 w-8 rounded-full flex items-center justify-center',
                done ? 'bg-atlasly-ok text-white' :
                  active ? 'bg-atlasly-teal text-white' :
                    'bg-atlasly-bg border border-atlasly-line text-atlasly-muted',
              )}>
                {done ? <CheckCircle className="h-4 w-4" /> :
                  active ? <Clock className="h-4 w-4" /> :
                    <Circle className="h-4 w-4" />}
              </div>
              <div className="mt-2 text-center">
                <p className={cn('text-xs font-medium', active ? 'text-atlasly-teal' : done ? 'text-atlasly-ok' : 'text-atlasly-muted')}>
                  {step.label}
                </p>
                {event && (
                  <p className="text-xs text-atlasly-muted mt-0.5">{formatDate(event.observed_at ?? event.occurred_at ?? event.created_at)}</p>
                )}
              </div>
            </div>
            {i < TIMELINE_STEPS.length - 1 && (
              <div className={cn('flex-1 h-px mt-4 mx-1', i < currentIndex ? 'bg-atlasly-ok' : 'bg-atlasly-line')} />
            )}
          </div>
        )
      })}
    </div>
  )
}
