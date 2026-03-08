import { DisciplineBadge } from '@/components/shared/StatusBadge'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'

interface Extraction {
  extraction_id?: string
  id?: string
  discipline?: string
  severity?: string
  code_ref?: string
  action_needed?: string
  description?: string
  confidence?: number
  status?: string
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-atlasly-bad/20 text-atlasly-bad',
  high: 'bg-atlasly-rust/20 text-atlasly-rust',
  medium: 'bg-atlasly-warn/20 text-atlasly-warn',
  low: 'bg-atlasly-ok/20 text-atlasly-ok',
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
            {onReview && <th className="text-left px-4 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Review</th>}
          </tr>
        </thead>
        <tbody>
          {extractions.map((ex, i) => {
            const id = ex.extraction_id ?? ex.id ?? String(i)
            const conf = typeof ex.confidence === 'number' ? Math.round(ex.confidence * 100) : null
            return (
              <tr key={id} className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/40">
                <td className="px-4 py-3">
                  {ex.discipline ? <DisciplineBadge discipline={ex.discipline} /> : <span className="text-atlasly-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {ex.severity ? (
                    <Badge colorClass={SEVERITY_COLORS[ex.severity.toLowerCase()] ?? 'bg-gray-100 text-gray-700'}>
                      {ex.severity}
                    </Badge>
                  ) : '—'}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-atlasly-ink">{ex.code_ref ?? '—'}</td>
                <td className="px-4 py-3 text-atlasly-muted max-w-xs truncate">
                  {ex.action_needed ?? ex.description ?? '—'}
                </td>
                <td className="px-4 py-3">
                  {conf !== null ? (
                    <div className="flex items-center gap-2">
                      <Progress value={conf} className="w-16 h-1.5" />
                      <span className="text-xs text-atlasly-muted">{conf}%</span>
                    </div>
                  ) : '—'}
                </td>
                {onReview && (
                  <td className="px-4 py-3">
                    {ex.status === 'pending' || !ex.status ? (
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => onReview(id, 'accept')}
                          className="text-xs px-2 py-1 rounded bg-atlasly-ok/15 text-atlasly-ok hover:bg-atlasly-ok/25"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => onReview(id, 'reject')}
                          className="text-xs px-2 py-1 rounded bg-atlasly-bad/15 text-atlasly-bad hover:bg-atlasly-bad/25"
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <Badge colorClass={ex.status === 'accepted' ? 'bg-atlasly-ok/15 text-atlasly-ok' : 'bg-atlasly-bad/15 text-atlasly-bad'}>
                        {ex.status}
                      </Badge>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
