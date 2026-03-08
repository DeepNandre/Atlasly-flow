import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle } from 'lucide-react'
import { useCommentLetters, useReviewExtraction, useApproveAndCreateTasks } from '@/hooks/useApi'
import { ExtractionTable } from '@/components/letters/ExtractionTable'
import { LetterStatusBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function LetterDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data, isLoading, error, refetch } = useCommentLetters()
  const review = useReviewExtraction()
  const approve = useApproveAndCreateTasks()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const letters: any[] = (data as any)?.letters ?? (Array.isArray(data) ? data : [])
  const letter = letters.find((l) => (l.letter_id ?? l.id) === id)

  const extractions = letter?.extractions ?? letter?.candidates ?? []
  const pendingCount = extractions.filter((e: { status?: string }) => !e.status || e.status === 'pending').length
  const canApprove = letter?.status === 'needs_review' && pendingCount === 0

  const handleReview = (extractionId: string, action: 'accept' | 'reject') => {
    if (!id) return
    review.mutate({ letter_id: id, extraction_id: extractionId, action }, { onSuccess: () => { refetch() } })
  }

  const handleApprove = () => {
    if (!id) return
    approve.mutate({ letter_id: id }, { onSuccess: () => navigate('/letters') })
  }

  if (error) return <ErrorState message="Could not load letter" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/letters')} className="text-atlasly-muted hover:text-atlasly-ink">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-atlasly-ink">
            {letter?.filename ?? letter?.name ?? 'Comment Letter'}
          </h1>
          <div className="flex items-center gap-2 mt-0.5">
            {letter?.status && <LetterStatusBadge status={letter.status} />}
            <span className="text-sm text-atlasly-muted">{extractions.length} extracted items</span>
          </div>
        </div>
        {letter?.status === 'needs_review' && (
          <Button
            onClick={handleApprove}
            disabled={!canApprove || approve.isPending}
            title={!canApprove ? 'Review all items before approving' : undefined}
          >
            <CheckCircle className="h-4 w-4 mr-1" />
            {approve.isPending ? 'Creating Tasks…' : 'Approve & Create Tasks'}
          </Button>
        )}
        {letter?.status === 'approved' || letter?.status === 'tasks_created' ? (
          <Button variant="outline" onClick={() => navigate('/tasks')}>
            View Tasks
          </Button>
        ) : null}
      </div>

      {pendingCount > 0 && letter?.status === 'needs_review' && (
        <div className="rounded-lg border border-atlasly-warn/40 bg-atlasly-warn/5 px-4 py-3">
          <p className="text-sm text-atlasly-warn font-medium">
            {pendingCount} item{pendingCount !== 1 ? 's' : ''} need review before you can approve this letter
          </p>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Extracted Comments</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={6} /></div>
          ) : (
            <ExtractionTable
              extractions={extractions}
              onReview={letter?.status === 'needs_review' ? handleReview : undefined}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
