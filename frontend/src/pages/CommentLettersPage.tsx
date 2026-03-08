import { useState } from 'react'
import { FileText, Plus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useCommentLetters } from '@/hooks/useApi'
import { LetterUpload } from '@/components/letters/LetterUpload'
import { EmptyState } from '@/components/shared/EmptyState'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { LetterStatusBadge } from '@/components/shared/StatusBadge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatDate } from '@/lib/utils'

function needsReview(status?: string) {
  return status === 'review_queueing' || status === 'human_review' || status === 'needs_review'
}

export default function CommentLettersPage() {
  const { data, isLoading, error, refetch } = useCommentLetters()
  const [uploadOpen, setUploadOpen] = useState(false)
  const navigate = useNavigate()

  const letters = ((data as { letters?: Array<Record<string, unknown>> } | undefined)?.letters ?? [])
  const reviewQueue = letters.filter((letter) => needsReview(String(letter.status ?? '')))

  if (error) return <ErrorState message="Could not load comment letters" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Comment Letters</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Upload, parse, and approve AHJ comment letters</p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Upload Letter
        </Button>
      </div>

      {reviewQueue.length > 0 && (
        <div className="rounded-lg border border-atlasly-rust/40 bg-atlasly-rust/5 p-4">
          <p className="text-sm font-semibold text-atlasly-rust mb-2">
            {reviewQueue.length} {reviewQueue.length === 1 ? 'letter needs' : 'letters need'} review
          </p>
          <div className="space-y-1.5">
            {reviewQueue.map((letter) => {
              const id = String(letter.letter_id ?? letter.id ?? '')
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => navigate(`/letters/${id}`)}
                  className="flex items-center gap-2 text-sm text-atlasly-rust hover:text-atlasly-ink transition-colors"
                >
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  {String(letter.source_filename ?? letter.filename ?? 'Comment letter')}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>All Letters</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-5"><SkeletonTable rows={5} /></div>
          ) : letters.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No comment letters yet"
              description="Upload your first AHJ comment letter to begin extracting action items"
              actionLabel="Upload Letter"
              onAction={() => setUploadOpen(true)}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-atlasly-line">
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">File</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Status</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Created</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Approved</th>
                  </tr>
                </thead>
                <tbody>
                  {letters.map((letter) => {
                    const id = String(letter.letter_id ?? letter.id ?? '')
                    const filename = String(letter.source_filename ?? letter.filename ?? 'Comment letter')
                    return (
                      <tr
                        key={id}
                        className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50 cursor-pointer"
                        onClick={() => navigate(`/letters/${id}`)}
                      >
                        <td className="px-5 py-3 font-medium text-atlasly-ink">
                          <div className="flex items-center gap-2">
                            <FileText className="h-3.5 w-3.5 text-atlasly-muted shrink-0" />
                            {filename}
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <LetterStatusBadge status={String(letter.status ?? 'parsing')} />
                        </td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(String(letter.created_at ?? ''))}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(String(letter.approved_at ?? ''))}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload Comment Letter</DialogTitle>
          </DialogHeader>
          <LetterUpload onSuccess={() => { setUploadOpen(false); refetch() }} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
