import { DisciplineBadge } from '@/components/shared/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'

interface Extraction {
  extraction_id?: string
  id?: string
  discipline?: string
  severity?: string
  code_ref?: string
  code_reference?: string
  action_needed?: string
  requested_action?: string
  description?: string
  confidence?: number
  status?: string
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-atlasly-bad/20 text-atlasly-bad',
  high: 'bg-atlasly-rust/20 text-atlasly-rust',
  major: 'bg-atlasly-rust/20 text-atlasly-rust',
  medium: 'bg-atlasly-warn/20 text-atlasly-warn',
  low: 'bg-atlasly-ok/20 text-atlasly-ok',
}

function canReview(status?: string) {
  return status === 'review_queueing' || status === 'human_review' || status === 'needs_review'
}

interface ExtractionTableProps {
  extractions: Extraction[]
  onReview?: (id: string, action: 'accept' | 'reject') => void
}

export function ExtractionTable({ extractions, onReview }: ExtractionTableProps) {
  if (extractions.length === 0) {
    return <p className="text-sm text-atlasly-muted py-6 text-center">No extractions yet</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-atlasly-line">
            <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Discipline</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Severity</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Code Ref</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Action Needed</th>
            <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide w-28">Confidence</th>
            {onReview ? <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Review</th> : null}
          </tr>
        </thead>
        <tbody>
          {extractions.map((extraction, index) => {
            const id = extraction.extraction_id ?? extraction.id ?? String(index)
            const confidence = typeof extraction.confidence === 'number' ? Math.round(extraction.confidence * 100) : null
            const status = extraction.status ?? ''
            return (
              <tr key={id} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40 align-top">
                <td className="px-4 py-3">
                  {extraction.discipline ? <DisciplineBadge discipline={extraction.discipline} /> : <span className="text-atlasly-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {extraction.severity ? (
                    <Badge colorClass={SEVERITY_COLORS[String(extraction.severity).toLowerCase()] ?? 'bg-gray-100 text-gray-700'}>
                      {extraction.severity}
                    </Badge>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-atlasly-ink">{extraction.code_reference ?? extraction.code_ref ?? '—'}</td>
                <td className="px-4 py-3 text-atlasly-muted max-w-lg">{extraction.requested_action ?? extraction.action_needed ?? extraction.description ?? '—'}</td>
                <td className="px-4 py-3">
                  {confidence !== null ? (
                    <div className="flex items-center gap-2">
                      <Progress value={confidence} className="w-16 h-1.5" />
                      <span className="text-xs text-atlasly-muted">{confidence}%</span>
                    </div>
                  ) : '—'}
                </td>
                {onReview ? (
                  <td className="px-4 py-3">
                    {canReview(status) ? (
                      <div className="flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => onReview(id, 'accept')}
                          className="text-xs px-2 py-1 rounded bg-atlasly-ok/15 text-atlasly-ok hover:bg-atlasly-ok/25"
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          onClick={() => onReview(id, 'reject')}
                          className="text-xs px-2 py-1 rounded bg-atlasly-bad/15 text-atlasly-bad hover:bg-atlasly-bad/25"
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <Badge colorClass="bg-atlasly-bg text-atlasly-muted">{status || 'processed'}</Badge>
                    )}
                  </td>
                ) : null}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
