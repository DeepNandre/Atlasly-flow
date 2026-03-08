import { Badge } from '@/components/ui/badge'
import {
  PERMIT_STATUSES,
  TASK_STATUSES,
  LETTER_STATUSES,
  PAYOUT_STATUSES,
  DISCIPLINES,
} from '@/lib/constants'

export function PermitStatusBadge({ status }: { status: string }) {
  const s = PERMIT_STATUSES[status as keyof typeof PERMIT_STATUSES]
  return <Badge colorClass={s?.color}>{s?.label ?? status}</Badge>
}

export function TaskStatusBadge({ status }: { status: string }) {
  const s = TASK_STATUSES[status as keyof typeof TASK_STATUSES]
  return <Badge colorClass={s?.color}>{s?.label ?? status}</Badge>
}

export function LetterStatusBadge({ status }: { status: string }) {
  const s = LETTER_STATUSES[status as keyof typeof LETTER_STATUSES]
  return <Badge colorClass={s?.color}>{s?.label ?? status}</Badge>
}

export function PayoutStatusBadge({ status }: { status: string }) {
  const s = PAYOUT_STATUSES[status as keyof typeof PAYOUT_STATUSES]
  return <Badge colorClass={s?.color}>{s?.label ?? status}</Badge>
}

export function DisciplineBadge({ discipline }: { discipline: string }) {
  const d = DISCIPLINES[discipline as keyof typeof DISCIPLINES]
  return <Badge colorClass={d?.color}>{d?.label ?? discipline}</Badge>
}
