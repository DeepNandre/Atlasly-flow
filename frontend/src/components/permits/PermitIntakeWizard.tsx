import { useMemo, useState } from 'react'
import { CheckCircle, FileText, MapPin, Send } from 'lucide-react'
import { useIntakeComplete, useResolveAhj } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const PERMIT_TYPES = [
  { value: 'commercial_ti', label: 'Commercial TI' },
  { value: 'electrical_service_upgrade', label: 'Electrical Service Upgrade' },
  { value: 'solar', label: 'Solar' },
  { value: 'ev_charger', label: 'EV Charger' },
]

const STEPS = [
  { id: 1, label: 'Project Details', icon: FileText },
  { id: 2, label: 'AHJ Resolution', icon: MapPin },
  { id: 3, label: 'Review Application', icon: CheckCircle },
  { id: 4, label: 'Submit', icon: Send },
]

interface FormData {
  project_name: string
  address_line1: string
  city: string
  state: string
  postal_code: string
  permit_type: string
  scope_summary: string
  valuation: string
  ahjId?: string
  ahjName?: string
}

export function PermitIntakeWizard({ onSuccess }: { onSuccess?: () => void }) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormData>({
    project_name: '',
    address_line1: '',
    city: '',
    state: 'CA',
    postal_code: '',
    permit_type: 'commercial_ti',
    scope_summary: '',
    valuation: '',
  })

  const resolveAhj = useResolveAhj()
  const intake = useIntakeComplete()
  const ahjResult = (resolveAhj.data as { resolved?: boolean; result?: Record<string, unknown> } | undefined)?.result

  const summaryAddress = useMemo(
    () => [form.address_line1, form.city, form.state, form.postal_code].filter(Boolean).join(', '),
    [form.address_line1, form.city, form.postal_code, form.state],
  )

  const update = (field: keyof FormData, value: string) => setForm((current) => ({ ...current, [field]: value }))

  const handleAhjLookup = () => {
    resolveAhj.mutate({
      address: {
        line1: form.address_line1,
        city: form.city,
        state: form.state,
        postal_code: form.postal_code,
      },
    }, {
      onSuccess: (payload) => {
        const result = (payload as { result?: Record<string, unknown> } | undefined)?.result ?? {}
        setForm((current) => ({
          ...current,
          ahjId: String(result.ahj_id ?? current.ahjId ?? ''),
          ahjName: String(result.name ?? result.ahj_name ?? current.ahjName ?? ''),
        }))
        setStep(3)
      },
    })
  }

  const handleSubmit = () => {
    intake.mutate({
      permit_type: form.permit_type,
      line1: form.address_line1,
      city: form.city,
      state: form.state,
      postal_code: form.postal_code,
      project_name: form.project_name,
      scope_summary: form.scope_summary,
      valuation_usd: Number(form.valuation || '0'),
      ahj_id: form.ahjId,
    }, { onSuccess })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-0">
        {STEPS.map((stepItem, index) => (
          <div key={stepItem.id} className="flex items-center flex-1 last:flex-none">
            <div className={cn(
              'flex items-center gap-1.5 text-xs font-medium',
              step === stepItem.id ? 'text-atlasly-teal' : step > stepItem.id ? 'text-atlasly-ok' : 'text-atlasly-muted',
            )}>
              <div className={cn(
                'h-6 w-6 rounded-full flex items-center justify-center text-xs border',
                step === stepItem.id ? 'border-atlasly-teal bg-atlasly-teal text-white' :
                  step > stepItem.id ? 'border-atlasly-ok bg-atlasly-ok text-white' :
                    'border-atlasly-line bg-atlasly-bg text-atlasly-muted',
              )}>
                {step > stepItem.id ? '✓' : stepItem.id}
              </div>
              <span className="hidden sm:inline">{stepItem.label}</span>
            </div>
            {index < STEPS.length - 1 && <div className={cn('flex-1 h-px mx-2', step > stepItem.id ? 'bg-atlasly-ok' : 'bg-atlasly-line')} />}
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project_name">Project Name</Label>
            <Input id="project_name" value={form.project_name} onChange={(event) => update('project_name', event.target.value)} placeholder="Battery + Solar Retrofit" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="address_line1">Street Address</Label>
            <Input id="address_line1" value={form.address_line1} onChange={(event) => update('address_line1', event.target.value)} placeholder="200 Market St" autoComplete="street-address" />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="city">City</Label>
              <Input id="city" value={form.city} onChange={(event) => update('city', event.target.value)} autoComplete="address-level2" />
            </div>
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="state">State</Label>
              <Input id="state" value={form.state} onChange={(event) => update('state', event.target.value)} autoComplete="address-level1" />
            </div>
            <div className="space-y-1.5 sm:col-span-1">
              <Label htmlFor="postal_code">ZIP</Label>
              <Input id="postal_code" value={form.postal_code} onChange={(event) => update('postal_code', event.target.value)} autoComplete="postal-code" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="permit_type">Permit Type</Label>
            <Select value={form.permit_type} onValueChange={(value) => update('permit_type', value)}>
              <SelectTrigger id="permit_type"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PERMIT_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="scope">Scope of Work</Label>
            <Textarea id="scope" value={form.scope_summary} onChange={(event) => update('scope_summary', event.target.value)} placeholder="Electrical service upgrade and rooftop solar retrofit." />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="valuation">Estimated Valuation ($)</Label>
            <Input id="valuation" type="number" value={form.valuation} onChange={(event) => update('valuation', event.target.value)} placeholder="250000" />
          </div>
          <Button onClick={() => setStep(2)} disabled={!form.project_name || !form.address_line1 || !form.city || !form.postal_code}>
            Continue to AHJ Resolution →
          </Button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div className="rounded-lg bg-atlasly-bg border border-atlasly-line p-4">
            <p className="text-sm text-atlasly-muted mb-1">Looking up jurisdiction for:</p>
            <p className="font-medium text-atlasly-ink">{summaryAddress}</p>
          </div>
          {ahjResult ? (
            <div className="rounded-lg bg-atlasly-teal/5 border border-atlasly-teal/30 p-4">
              <p className="text-xs font-semibold text-atlasly-teal uppercase tracking-wide mb-1">Resolved Jurisdiction</p>
              <p className="font-medium text-atlasly-ink">{String(ahjResult.name ?? ahjResult.ahj_name ?? 'AHJ found')}</p>
              <p className="text-xs text-atlasly-muted mt-1">{String(ahjResult.ahj_id ?? '')}</p>
            </div>
          ) : null}
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => setStep(1)}>← Back</Button>
            <Button onClick={handleAhjLookup} disabled={resolveAhj.isPending}>
              {resolveAhj.isPending ? 'Looking up…' : 'Look Up AHJ'}
            </Button>
            {ahjResult ? <Button onClick={() => setStep(3)}>Continue →</Button> : null}
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4">
          <p className="text-sm text-atlasly-muted">Review the application details before submitting.</p>
          <div className="rounded-lg border border-atlasly-line bg-atlasly-bg divide-y divide-atlasly-line">
            {[
              ['Project', form.project_name],
              ['Address', summaryAddress],
              ['Permit Type', PERMIT_TYPES.find((type) => type.value === form.permit_type)?.label ?? form.permit_type],
              ['Scope', form.scope_summary || '—'],
              ['Valuation', form.valuation ? `$${Number(form.valuation).toLocaleString()}` : '—'],
              ['Jurisdiction', form.ahjName ?? String(ahjResult?.name ?? 'Not resolved')],
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

      {step === 4 && (
        <div className="space-y-4">
          <div className="rounded-lg bg-atlasly-teal/5 border border-atlasly-teal/20 p-5 text-center">
            <Send className="h-8 w-8 text-atlasly-teal mx-auto mb-2" />
            <p className="font-semibold text-atlasly-ink">Ready to submit</p>
            <p className="text-sm text-atlasly-muted mt-1">This will generate the permit intake session and application draft.</p>
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
