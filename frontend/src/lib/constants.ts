export const ROUTES = {
  DASHBOARD: '/',
  LETTERS: '/letters',
  LETTER_DETAIL: '/letters/:id',
  TASKS: '/tasks',
  PERMITS: '/permits',
  PERMIT_DETAIL: '/permits/:id',
  PAYOUTS: '/payouts',
  INTEGRATIONS: '/integrations',
  SETTINGS: '/settings',
} as const

export const ROLES = {
  OWNER: 'owner',
  ADMIN: 'admin',
  PM: 'pm',
  REVIEWER: 'reviewer',
  SUBCONTRACTOR: 'subcontractor',
} as const

export type Role = typeof ROLES[keyof typeof ROLES]

export const ADMIN_ROLES: Role[] = [ROLES.OWNER, ROLES.ADMIN]
export const WORK_ROLES: Role[] = [ROLES.OWNER, ROLES.ADMIN, ROLES.PM, ROLES.REVIEWER]
export const ALL_ROLES: Role[] = Object.values(ROLES)

export const PERMIT_STATUSES = {
  draft: { label: 'Draft', color: 'bg-atlasly-muted/20 text-atlasly-muted' },
  submitted: { label: 'Submitted', color: 'bg-blue-100 text-blue-700' },
  under_review: { label: 'Under Review', color: 'bg-atlasly-warn/20 text-atlasly-warn' },
  in_review: { label: 'In Review', color: 'bg-atlasly-warn/20 text-atlasly-warn' },
  approved: { label: 'Approved', color: 'bg-atlasly-teal/20 text-atlasly-teal' },
  issued: { label: 'Issued', color: 'bg-atlasly-ok/20 text-atlasly-ok' },
  rejected: { label: 'Rejected', color: 'bg-atlasly-bad/20 text-atlasly-bad' },
} as const

export const TASK_STATUSES = {
  open: { label: 'Open', color: 'bg-blue-100 text-blue-700' },
  in_progress: { label: 'In Progress', color: 'bg-atlasly-warn/20 text-atlasly-warn' },
  resolved: { label: 'Resolved', color: 'bg-atlasly-ok/20 text-atlasly-ok' },
  escalated: { label: 'Escalated', color: 'bg-atlasly-bad/20 text-atlasly-bad' },
  blocked: { label: 'Blocked', color: 'bg-atlasly-rust/20 text-atlasly-rust' },
  done: { label: 'Done', color: 'bg-atlasly-ok/20 text-atlasly-ok' },
} as const

export const DISCIPLINES = {
  electrical: { label: 'Electrical', color: 'bg-yellow-100 text-yellow-700' },
  mechanical: { label: 'Mechanical', color: 'bg-orange-100 text-orange-700' },
  plumbing: { label: 'Plumbing', color: 'bg-blue-100 text-blue-700' },
  structural: { label: 'Structural', color: 'bg-slate-100 text-slate-700' },
  fire: { label: 'Fire & Life Safety', color: 'bg-red-100 text-red-700' },
  civil: { label: 'Civil', color: 'bg-green-100 text-green-700' },
  general: { label: 'General', color: 'bg-gray-100 text-gray-700' },
} as const

export const LETTER_STATUSES = {
  parsing: { label: 'Parsing…', color: 'bg-atlasly-warn/20 text-atlasly-warn' },
  needs_review: { label: 'Needs Review', color: 'bg-atlasly-rust/20 text-atlasly-rust' },
  review_queueing: { label: 'Queued for Review', color: 'bg-atlasly-rust/20 text-atlasly-rust' },
  human_review: { label: 'In Review', color: 'bg-atlasly-rust/20 text-atlasly-rust' },
  auto_accepted: { label: 'Auto Accepted', color: 'bg-atlasly-teal/20 text-atlasly-teal' },
  approved: { label: 'Approved', color: 'bg-atlasly-ok/20 text-atlasly-ok' },
  tasks_created: { label: 'Tasks Created', color: 'bg-atlasly-teal/20 text-atlasly-teal' },
} as const

export const PAYOUT_STATUSES = {
  created: { label: 'Created', color: 'bg-gray-100 text-gray-700' },
  submitted: { label: 'Submitted', color: 'bg-blue-100 text-blue-700' },
  settled: { label: 'Settled', color: 'bg-atlasly-ok/20 text-atlasly-ok' },
  reversed: { label: 'Reversed', color: 'bg-atlasly-bad/20 text-atlasly-bad' },
} as const

export const ACTIVITY_LABELS: Record<string, string> = {
  'permit.status_changed': 'Permit status updated',
  'task.created': 'Task created',
  'task.auto_assigned': 'Task auto-assigned',
  'task.escalated': 'Task escalated',
  'comment_letter.parsing_started': 'Comment letter processing started',
  'comment_letter.approved': 'Comment letter approved',
  'permit.application_generated': 'Permit application generated',
  'intake.completed': 'Permit intake completed',
  'payout.created': 'Payout instruction created',
  'payout.settled': 'Payout settled',
  'connector.synced': 'City connector synced',
}
