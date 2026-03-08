import { useState } from 'react'
import { AlertTriangle, TrendingUp, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { usePayoutPreflight, useCreatePayout } from '@/hooks/useApi'
import { cn } from '@/lib/utils'

interface PayoutFormProps {
  onSuccess?: () => void
}

export function PayoutForm({ onSuccess }: PayoutFormProps) {
  const [amount, setAmount] = useState('')
  const [permitId, setPermitId] = useState('')
  const [recipient, setRecipient] = useState('')

  const preflight = usePayoutPreflight()
  const createPayout = useCreatePayout()

  const handlePreflight = () => {
    preflight.mutate({ amount: Number(amount), permit_id: permitId, recipient })
  }

  const handleCreate = () => {
    createPayout.mutate(
      { amount: Number(amount), permit_id: permitId, recipient },
      { onSuccess },
    )
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const preflightResult = preflight.data as Record<string, any> | null | undefined
  const risk = preflightResult?.risk_score ?? preflightResult?.risk ?? null
  const riskLevel = risk === null ? null : risk < 0.3 ? 'low' : risk < 0.7 ? 'medium' : 'high'

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="permit-id">Permit ID</Label>
        <Input id="permit-id" value={permitId} onChange={(e) => setPermitId(e.target.value)} placeholder="permit_xxxx" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="recipient">Recipient</Label>
        <Input id="recipient" value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Contractor ID or email" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="amount">Amount ($)</Label>
        <Input id="amount" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
      </div>

      {/* Preflight */}
      {!preflightResult ? (
        <Button variant="outline" onClick={handlePreflight} disabled={!amount || !permitId || preflight.isPending}>
          {preflight.isPending ? 'Running risk check…' : 'Run Risk Check'}
        </Button>
      ) : (
        <div className={cn(
          'rounded-lg border p-4',
          riskLevel === 'low' ? 'border-atlasly-ok/40 bg-atlasly-ok/5' :
            riskLevel === 'medium' ? 'border-atlasly-warn/40 bg-atlasly-warn/5' :
              'border-atlasly-bad/40 bg-atlasly-bad/5',
        )}>
          <div className="flex items-center gap-2 mb-1">
            {riskLevel === 'low' ? <ShieldCheck className="h-4 w-4 text-atlasly-ok" /> :
              riskLevel === 'medium' ? <TrendingUp className="h-4 w-4 text-atlasly-warn" /> :
                <AlertTriangle className="h-4 w-4 text-atlasly-bad" />}
            <span className={cn(
              'text-sm font-semibold capitalize',
              riskLevel === 'low' ? 'text-atlasly-ok' :
                riskLevel === 'medium' ? 'text-atlasly-warn' : 'text-atlasly-bad',
            )}>
              {riskLevel} risk — score {typeof risk === 'number' ? (risk * 100).toFixed(0) : '—'}%
            </span>
          </div>
          {(preflightResult?.reasons as string[] | undefined)?.map((r: string, i: number) => (
            <p key={i} className="text-xs text-atlasly-muted mt-0.5">• {r}</p>
          ))}
        </div>
      )}

      {preflightResult != null && (
        <Button onClick={handleCreate} disabled={createPayout.isPending || riskLevel === 'high'} title={riskLevel === 'high' ? 'High risk — resolve issues before proceeding' : undefined}>
          {createPayout.isPending ? 'Creating…' : 'Create Payout Instruction'}
        </Button>
      )}
    </div>
  )
}
