import { useState, useCallback } from 'react'
import { Upload, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useUploadLetter, useParseComments } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

export function LetterUpload({ onSuccess }: { onSuccess?: () => void }) {
  const [dragging, setDragging] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const upload = useUploadLetter()
  const parse = useParseComments()

  const handleFile = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      const b64 = (reader.result as string).split(',')[1]
      upload.mutate(
        { filename: file.name, content_b64: b64 },
        { onSuccess: onSuccess },
      )
    }
    reader.readAsDataURL(file)
  }, [upload, onSuccess])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }, [handleFile])

  const onFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const handleParseText = () => {
    if (!pasteText.trim()) return
    parse.mutate({ raw_text: pasteText }, { onSuccess: () => { setPasteText(''); onSuccess?.() } })
  }

  return (
    <Tabs defaultValue="upload">
      <TabsList>
        <TabsTrigger value="upload">Upload PDF</TabsTrigger>
        <TabsTrigger value="paste">Paste Text</TabsTrigger>
      </TabsList>

      <TabsContent value="upload">
        <label
          className={cn(
            'mt-2 flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 cursor-pointer transition-colors',
            dragging ? 'border-atlasly-teal bg-atlasly-teal/5' : 'border-atlasly-line hover:border-atlasly-teal/50 hover:bg-atlasly-bg',
          )}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <input type="file" accept=".pdf,.txt" className="sr-only" onChange={onFileInput} />
          <Upload className="h-8 w-8 text-atlasly-muted mb-3" />
          <p className="text-sm font-medium text-atlasly-ink">Drop your comment letter here</p>
          <p className="text-xs text-atlasly-muted mt-1">or click to browse — PDF or TXT</p>
          {upload.isPending && (
            <p className="text-xs text-atlasly-teal mt-3 animate-pulse">Uploading…</p>
          )}
        </label>
      </TabsContent>

      <TabsContent value="paste" className="mt-2 space-y-3">
        <Textarea
          placeholder="Paste the raw text of the comment letter here…"
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          className="min-h-[160px]"
        />
        <Button
          onClick={handleParseText}
          disabled={!pasteText.trim() || parse.isPending}
        >
          <FileText className="h-4 w-4 mr-1" />
          {parse.isPending ? 'Processing…' : 'Extract Comments'}
        </Button>
      </TabsContent>
    </Tabs>
  )
}
