import { useState } from 'react'
import { AlertTriangle, ShieldCheck, TrendingUp } from 'lucide-react'
import { useCreatePayout, usePayoutPreflight } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface PayoutFormProps {
  onSuccess?: () => void
}

export function PayoutForm({ onSuccess }: PayoutFormProps) {
  const [amount, setAmount] = useState('')
  const [beneficiaryId, setBeneficiaryId] = useState('beneficiary-demo')

  const preflight = usePayoutPreflight()
  const createPayout = useCreatePayout()

  const preflightResult = preflight.data as {
    risk_score?: number
    risk_band?: 'low' | 'medium' | 'high'
    recommended_actions?: Array<{ action_text?: string }>
  } | undefined
  const riskBand = preflightResult?.risk_band ?? 'high'

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="beneficiary-id">Beneficiary ID</Label>
        <Input id="beneficiary-id" value={beneficiaryId} onChange={(event) => setBeneficiaryId(event.target.value)} placeholder="beneficiary-demo" autoComplete="off" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="amount">Amount ($)</Label>
        <Input id="amount" type="number" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="1200" />
      </div>

      {!preflightResult ? (
        <Button variant="outline" onClick={() => preflight.mutate()} disabled={!amount || preflight.isPending}>
          {preflight.isPending ? 'Running risk check…' : 'Run Risk Check'}
        </Button>
      ) : (
        <div className={cn(
          'rounded-lg border p-4',
          riskBand === 'low' ? 'border-atlasly-ok/40 bg-atlasly-ok/5' : riskBand === 'medium' ? 'border-atlasly-warn/40 bg-atlasly-warn/5' : 'border-atlasly-bad/40 bg-atlasly-bad/5',
        )}>
          <div className="flex items-center gap-2 mb-1">
            {riskBand === 'low' ? <ShieldCheck className="h-4 w-4 text-atlasly-ok" /> : riskBand === 'medium' ? <TrendingUp className="h-4 w-4 text-atlasly-warn" /> : <AlertTriangle className="h-4 w-4 text-atlasly-bad" />}
            <span className={cn('text-sm font-semibold capitalize', riskBand === 'low' ? 'text-atlasly-ok' : riskBand === 'medium' ? 'text-atlasly-warn' : 'text-atlasly-bad')}>
              {riskBand} risk — score {typeof preflightResult.risk_score === 'number' ? `${Math.round(preflightResult.risk_score * 100)}%` : '—'}
            </span>
          </div>
          {(preflightResult.recommended_actions ?? []).map((action, index) => (
            <p key={index} className="text-xs text-atlasly-muted mt-0.5">• {action.action_text ?? 'Recommended mitigation available.'}</p>
          ))}
        </div>
      )}

      {preflightResult ? (
        <Button
          onClick={() => createPayout.mutate({ amount: Number(amount), beneficiary_id: beneficiaryId }, { onSuccess })}
          disabled={createPayout.isPending || riskBand === 'high'}
          title={riskBand === 'high' ? 'High risk payout. Resolve the preflight issues first.' : undefined}
        >
          {createPayout.isPending ? 'Creating…' : 'Create Payout Instruction'}
        </Button>
      ) : null}
    </div>
  )
}
