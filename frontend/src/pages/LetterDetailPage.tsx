import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle } from 'lucide-react'
import { useApproveAndCreateTasks, useCommentLetters, useLetterExtractions, useReviewExtraction } from '@/hooks/useApi'
import { ExtractionTable } from '@/components/letters/ExtractionTable'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { LetterStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function requiresReview(status?: string) {
  return status === 'review_queueing' || status === 'human_review' || status === 'needs_review'
}

export default function LetterDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const letters = useCommentLetters()
  const extractionQuery = useLetterExtractions(id)
  const review = useReviewExtraction()
  const approve = useApproveAndCreateTasks()

  const letterRows = ((letters.data as { letters?: Array<Record<string, unknown>> } | undefined)?.letters ?? [])
  const letter = letterRows.find((row) => String(row.letter_id ?? row.id ?? '') === id)
  const extractions = useMemo(
    () => ((extractionQuery.data as { extractions?: Array<Record<string, unknown>> } | undefined)?.extractions ?? []),
    [extractionQuery.data],
  )
  const pendingCount = extractions.filter((row) => requiresReview(String(row.status ?? ''))).length
  const canApprove = Boolean(id && letter && requiresReview(String(letter.status ?? '')) && pendingCount === 0)

  const error = letters.error ?? extractionQuery.error
  if (error) return <ErrorState message="Could not load letter" onRetry={() => { letters.refetch(); extractionQuery.refetch() }} />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => navigate('/letters')} className="text-atlasly-muted hover:text-atlasly-ink" aria-label="Back to comment letters">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-atlasly-ink">{String(letter?.source_filename ?? 'Comment Letter')}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            {letter?.status ? <LetterStatusBadge status={String(letter.status)} /> : null}
            <span className="text-sm text-atlasly-muted">{extractions.length} extracted items</span>
          </div>
        </div>
        {requiresReview(String(letter?.status ?? '')) ? (
          <Button
            onClick={() => id && approve.mutate({ letter_id: id }, { onSuccess: () => navigate('/tasks') })}
            disabled={!canApprove || approve.isPending}
            title={!canApprove ? 'Resolve remaining review items before approving' : undefined}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            {approve.isPending ? 'Creating Tasks…' : 'Approve & Create Tasks'}
          </Button>
        ) : (
          <Button variant="outline" onClick={() => navigate('/tasks')}>View Tasks</Button>
        )}
      </div>

      {pendingCount > 0 && requiresReview(String(letter?.status ?? '')) && (
        <div className="rounded-lg border border-atlasly-warn/40 bg-atlasly-warn/5 px-4 py-3">
          <p className="text-sm text-atlasly-warn font-medium">
            {pendingCount} item{pendingCount !== 1 ? 's' : ''} still need review before approval
          </p>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Extracted Comments</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {extractionQuery.isLoading ? (
            <div className="p-5"><SkeletonTable rows={6} /></div>
          ) : (
            <ExtractionTable
              extractions={extractions}
              onReview={requiresReview(String(letter?.status ?? '')) ? (extractionId, action) => {
                if (!id) return
                review.mutate({ letter_id: id, extraction_id: extractionId, action }, { onSuccess: () => extractionQuery.refetch() })
              } : undefined}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
