import { useState } from 'react'
import { Plus, FileText } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useCommentLetters } from '@/hooks/useApi'
import { LetterStatusBadge } from '@/components/shared/StatusBadge'
import { ErrorState } from '@/components/shared/ErrorState'
import { SkeletonTable } from '@/components/shared/Skeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LetterUpload } from '@/components/letters/LetterUpload'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatDate } from '@/lib/utils'

export default function CommentLettersPage() {
  const { data, isLoading, error, refetch } = useCommentLetters()
  const [uploadOpen, setUploadOpen] = useState(false)
  const navigate = useNavigate()

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const letters: any[] = (data as any)?.letters ?? (Array.isArray(data) ? data : [])

  const needsReview = letters.filter((l) => l.status === 'needs_review')

  if (error) return <ErrorState message="Could not load comment letters" onRetry={refetch} />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-atlasly-ink">Comment Letters</h1>
          <p className="text-sm text-atlasly-muted mt-0.5">Upload and process AHJ comment letters</p>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Upload Letter
        </Button>
      </div>

      {/* Needs review queue */}
      {needsReview.length > 0 && (
        <div className="rounded-lg border border-atlasly-rust/40 bg-atlasly-rust/5 p-4">
          <p className="text-sm font-semibold text-atlasly-rust mb-2">
            {needsReview.length} {needsReview.length === 1 ? 'letter needs' : 'letters need'} review
          </p>
          <div className="space-y-1.5">
            {needsReview.map((l) => (
              <button
                key={l.letter_id ?? l.id}
                onClick={() => navigate(`/letters/${l.letter_id ?? l.id}`)}
                className="flex items-center gap-2 text-sm text-atlasly-rust hover:text-atlasly-ink transition-colors"
              >
                <FileText className="h-3.5 w-3.5 shrink-0" />
                {l.filename ?? l.name ?? 'Comment letter'} — {l.extraction_count ?? 0} items
              </button>
            ))}
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
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Items</th>
                    <th className="text-left px-5 py-3 text-xs font-semibold text-atlasly-muted uppercase tracking-wide">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {letters.map((l) => {
                    const id = l.letter_id ?? l.id
                    return (
                      <tr
                        key={id}
                        className="border-b border-atlasly-line last:border-0 hover:bg-atlasly-bg/50 cursor-pointer"
                        onClick={() => navigate(`/letters/${id}`)}
                      >
                        <td className="px-5 py-3 font-medium text-atlasly-ink">
                          <div className="flex items-center gap-2">
                            <FileText className="h-3.5 w-3.5 text-atlasly-muted shrink-0" />
                            {l.filename ?? l.name ?? 'Comment letter'}
                          </div>
                        </td>
                        <td className="px-5 py-3">
                          <LetterStatusBadge status={l.status ?? 'parsing'} />
                        </td>
                        <td className="px-5 py-3 text-atlasly-muted">{l.extraction_count ?? l.items ?? '—'}</td>
                        <td className="px-5 py-3 text-atlasly-muted">{formatDate(l.created_at)}</td>
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
