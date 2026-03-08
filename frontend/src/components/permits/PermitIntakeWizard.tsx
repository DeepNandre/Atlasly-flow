import { useState } from 'react'
import { CheckCircle, MapPin, FileText, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useIntakeComplete, useResolveAhj } from '@/hooks/useApi'
import { cn } from '@/lib/utils'

const PERMIT_TYPES = [
  'new_construction', 'addition', 'alteration', 'demolition',
  'electrical', 'mechanical', 'plumbing', 'fire_alarm', 'sprinkler',
]

const STEPS = [
  { id: 1, label: 'Project Details', icon: FileText },
  { id: 2, label: 'AHJ Resolution', icon: MapPin },
  { id: 3, label: 'Review Application', icon: CheckCircle },
  { id: 4, label: 'Submit', icon: Send },
]

interface FormData {
  project_name: string
  address: string
  permit_type: string
  scope_summary: string
  valuation: string
  ahj?: { name?: string; state?: string; jurisdiction_id?: string }
}

export function PermitIntakeWizard({ onSuccess }: { onSuccess?: () => void }) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormData>({
    project_name: '', address: '', permit_type: '', scope_summary: '', valuation: '',
  })

  const resolveAhj = useResolveAhj()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ahjResult = resolveAhj.data as Record<string, any> | null | undefined
  const intake = useIntakeComplete()

  const set = (field: keyof FormData, value: string) =>
    setForm((f) => ({ ...f, [field]: value }))

  const handleAhjLookup = () => {
    if (!form.address) return
    resolveAhj.mutate({ address: form.address }, {
      onSuccess: (data) => {
        setForm((f) => ({ ...f, ahj: data as { name?: string; state?: string; jurisdiction_id?: string } }))
        setStep(3)
      },
    })
  }

  const handleSubmit = () => {
    intake.mutate({
      project_name: form.project_name,
      address: form.address,
      permit_type: form.permit_type,
      scope_summary: form.scope_summary,
      valuation: Number(form.valuation),
      jurisdiction_id: form.ahj?.jurisdiction_id,
    }, { onSuccess })
  }

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center gap-0">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            <div className={cn(
              'flex items-center gap-1.5 text-xs font-medium',
              step === s.id ? 'text-atlasly-teal' : step > s.id ? 'text-atlasly-ok' : 'text-atlasly-muted',
            )}>
              <div className={cn(
                'h-6 w-6 rounded-full flex items-center justify-center text-xs border',
                step === s.id ? 'border-atlasly-teal bg-atlasly-teal text-white' :
                  step > s.id ? 'border-atlasly-ok bg-atlasly-ok text-white' :
                    'border-atlasly-line bg-atlasly-bg text-atlasly-muted',
              )}>
                {step > s.id ? '✓' : s.id}
              </div>
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={cn('flex-1 h-px mx-2', step > s.id ? 'bg-atlasly-ok' : 'bg-atlasly-line')} />
            )}
          </div>
        ))}
      </div>

      {/* Step 1: Project details */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project_name">Project Name</Label>
            <Input id="project_name" value={form.project_name} onChange={(e) => set('project_name', e.target.value)} placeholder="e.g. 123 Main St Office Renovation" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="address">Project Address</Label>
            <Input id="address" value={form.address} onChange={(e) => set('address', e.target.value)} placeholder="Full street address including city, state, ZIP" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit_type">Permit Type</Label>
            <Select value={form.permit_type} onValueChange={(v) => set('permit_type', v)}>
              <SelectTrigger id="permit_type"><SelectValue placeholder="Select permit type" /></SelectTrigger>
              <SelectContent>
                {PERMIT_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>{t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="scope">Scope of Work</Label>
            <Textarea id="scope" value={form.scope_summary} onChange={(e) => set('scope_summary', e.target.value)} placeholder="Briefly describe the work to be performed…" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="valuation">Estimated Valuation ($)</Label>
            <Input id="valuation" type="number" value={form.valuation} onChange={(e) => set('valuation', e.target.value)} placeholder="0" />
          </div>
          <Button
            onClick={() => setStep(2)}
            disabled={!form.project_name || !form.address || !form.permit_type}
          >
            Continue to AHJ Resolution →
          </Button>
        </div>
      )}

      {/* Step 2: AHJ resolution */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="rounded-lg bg-atlasly-bg border border-atlasly-line p-4">
            <p className="text-sm text-atlasly-muted mb-1">Looking up jurisdiction for:</p>
            <p className="font-medium text-atlasly-ink">{form.address}</p>
          </div>
          {ahjResult != null && (
            <div className="rounded-lg bg-atlasly-teal/5 border border-atlasly-teal/30 p-4">
              <p className="text-xs font-semibold text-atlasly-teal uppercase tracking-wide mb-1">Resolved Jurisdiction</p>
              <p className="font-medium text-atlasly-ink">{String(ahjResult?.name ?? 'AHJ found')}</p>
            </div>
          )}
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => setStep(1)}>← Back</Button>
            <Button onClick={handleAhjLookup} disabled={resolveAhj.isPending}>
              {resolveAhj.isPending ? 'Looking up…' : 'Look Up AHJ'}
            </Button>
            {ahjResult != null && (
              <Button onClick={() => setStep(3)}>Continue →</Button>
            )}
          </div>
        </div>
      )}

      {/* Step 3: Form review */}
      {step === 3 && (
        <div className="space-y-4">
          <p className="text-sm text-atlasly-muted">Review the application details before submitting.</p>
          <div className="rounded-lg border border-atlasly-line bg-atlasly-bg divide-y divide-atlasly-line">
            {[
              ['Project', form.project_name],
              ['Address', form.address],
              ['Permit Type', form.permit_type.replace(/_/g, ' ')],
              ['Scope', form.scope_summary],
              ['Valuation', form.valuation ? `$${Number(form.valuation).toLocaleString()}` : '—'],
              ['Jurisdiction', form.ahj?.name ?? form.ahj?.state ?? 'Not resolved'],
            ].map(([label, value]) => (
              <div key={label} className="flex gap-4 px-4 py-3">
                <span className="text-xs font-medium text-atlasly-muted w-24 shrink-0">{label}</span>
                <span className="text-sm text-atlasly-ink">{value}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => setStep(2)}>← Back</Button>
            <Button onClick={() => setStep(4)}>Looks good →</Button>
          </div>
        </div>
      )}

      {/* Step 4: Submit */}
      {step === 4 && (
        <div className="space-y-4">
          <div className="rounded-lg bg-atlasly-teal/5 border border-atlasly-teal/20 p-5 text-center">
            <Send className="h-8 w-8 text-atlasly-teal mx-auto mb-2" />
            <p className="font-semibold text-atlasly-ink">Ready to submit</p>
            <p className="text-sm text-atlasly-muted mt-1">This will generate the permit application and send it to the AHJ.</p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => setStep(3)}>← Back</Button>
            <Button onClick={handleSubmit} disabled={intake.isPending}>
              {intake.isPending ? 'Submitting…' : 'Submit Permit Application'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
