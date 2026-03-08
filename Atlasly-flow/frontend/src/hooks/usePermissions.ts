import { ADMIN_ROLES, WORK_ROLES, type Role } from '@/lib/constants'

export function usePermissions(role: Role) {
  const isAdmin = ADMIN_ROLES.includes(role)
  const isWorkRole = WORK_ROLES.includes(role)
  const isSubcontractor = role === 'subcontractor'

  return {
    canViewDashboard: isWorkRole,
    canViewLetters: isWorkRole,
    canViewTasks: true,
    canViewPermits: isWorkRole,
    canViewPayouts: isAdmin,
    canViewIntegrations: isAdmin,
    canViewSettings: isAdmin,
    canApproveLetters: ['owner', 'admin', 'pm'].includes(role),
    canAssignTasks: ['owner', 'admin', 'pm'].includes(role),
    canCreatePayout: isAdmin,
    canRotateCredentials: role === 'owner',
    canExportAudit: isAdmin,
    isAdmin,
    isSubcontractor,
  }
}
