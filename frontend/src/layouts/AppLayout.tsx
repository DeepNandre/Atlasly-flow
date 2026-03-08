import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, FileText, CheckSquare, Building2, DollarSign,
  Settings, Plug, ChevronDown, Menu, X, HelpCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/hooks/useAuth'
import { usePermissions } from '@/hooks/usePermissions'
import { DemoToolbar } from '@/components/shared/DemoToolbar'
import type { Role } from '@/lib/constants'
import { cn } from '@/lib/utils'

const NAV_WORK = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/letters', label: 'Comment Letters', icon: FileText },
  { to: '/tasks', label: 'Tasks', icon: CheckSquare },
  { to: '/permits', label: 'Permits', icon: Building2 },
]

const NAV_FINANCE = [
  { to: '/payouts', label: 'Payouts', icon: DollarSign },
]

const NAV_ADMIN = [
  { to: '/integrations', label: 'Integrations', icon: Plug },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const ROLE_LABELS: Record<Role, string> = {
  owner: 'Owner',
  admin: 'Admin',
  pm: 'Project Manager',
  reviewer: 'Reviewer',
  subcontractor: 'Subcontractor',
}

function NavItem({ to, label, icon: Icon, exact }: { to: string; label: string; icon: typeof LayoutDashboard; exact?: boolean }) {
  return (
    <NavLink
      to={to}
      end={exact}
      className={({ isActive }) => cn(
        'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
        isActive ? 'bg-atlasly-teal/15 text-atlasly-teal' : 'text-atlasly-muted hover:bg-atlasly-bg hover:text-atlasly-ink',
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </NavLink>
  )
}

export function AppLayout() {
  const { role, switchRole, ready } = useAuth()
  const perms = usePermissions(role)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)
  const [roleSwitching, setRoleSwitching] = useState(false)
  const location = useLocation()
  const isDemo = new URLSearchParams(location.search).has('demo')

  if (!ready) {
    return (
      <div className="flex items-center justify-center h-screen bg-atlasly-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-atlasly-teal border-t-transparent animate-spin" />
          <p className="text-sm text-atlasly-muted">Setting up your workspace…</p>
        </div>
      </div>
    )
  }

  const handleRoleSwitch = async (nextRole: Role) => {
    try {
      setRoleSwitching(true)
      await switchRole(nextRole)
      setUserMenuOpen(false)
      toast.success(`Switched to ${ROLE_LABELS[nextRole]}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not switch role')
    } finally {
      setRoleSwitching(false)
    }
  }

  const sidebar = (
    <nav className="flex flex-col h-full">
      <div className="px-4 py-5 border-b border-atlasly-line">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-md bg-atlasly-teal flex items-center justify-center text-white text-xs font-bold">A</div>
          <span className="font-semibold text-atlasly-ink text-sm">Atlasly</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        <div>
          <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-atlasly-muted">Work</p>
          <div className="space-y-0.5">
            {NAV_WORK.map((item) => <NavItem key={item.to} {...item} />)}
          </div>
        </div>

        {perms.canViewPayouts ? (
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-atlasly-muted">Finance</p>
            <div className="space-y-0.5">
              {NAV_FINANCE.map((item) => <NavItem key={item.to} {...item} />)}
            </div>
          </div>
        ) : null}

        {perms.isAdmin ? (
          <div>
            <p className="px-3 mb-1 text-[10px] font-semibold uppercase tracking-widest text-atlasly-muted">Admin</p>
            <div className="space-y-0.5">
              {NAV_ADMIN.map((item) => <NavItem key={item.to} {...item} />)}
            </div>
          </div>
        ) : null}
      </div>

      <div className="px-3 py-4 border-t border-atlasly-line relative">
        <button
          type="button"
          onClick={() => setUserMenuOpen((open) => !open)}
          className="flex items-center gap-2.5 w-full rounded-md px-3 py-2 hover:bg-atlasly-bg transition-colors"
          aria-haspopup="menu"
          aria-expanded={userMenuOpen}
        >
          <div className="h-7 w-7 rounded-full bg-atlasly-slate flex items-center justify-center text-white text-xs font-bold shrink-0">
            {role[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-xs font-medium text-atlasly-ink truncate">{ROLE_LABELS[role]}</p>
          </div>
          <ChevronDown className={cn('h-3.5 w-3.5 text-atlasly-muted transition-transform', userMenuOpen && 'rotate-180')} />
        </button>

        {userMenuOpen ? (
          <div className="absolute bottom-full left-3 right-3 mb-1 rounded-md border border-atlasly-line bg-atlasly-paper shadow-lg py-1 z-50">
            <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-atlasly-muted">Switch role</p>
            {(['owner', 'admin', 'pm', 'reviewer', 'subcontractor'] as Role[]).map((nextRole) => (
              <button
                key={nextRole}
                type="button"
                onClick={() => handleRoleSwitch(nextRole)}
                disabled={roleSwitching}
                className={cn(
                  'flex items-center gap-2 w-full px-3 py-1.5 text-sm hover:bg-atlasly-bg disabled:opacity-60',
                  nextRole === role ? 'text-atlasly-teal font-medium' : 'text-atlasly-ink',
                )}
              >
                {ROLE_LABELS[nextRole]}
                {nextRole === role ? <span className="ml-auto text-xs">✓</span> : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </nav>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-atlasly-bg">
      <aside className="hidden md:flex w-56 flex-col border-r border-atlasly-line bg-atlasly-paper shrink-0">
        {sidebar}
      </aside>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
          <button type="button" className="absolute inset-0 bg-atlasly-ink/50" onClick={() => setMobileOpen(false)} aria-label="Close navigation overlay" />
          <aside className="absolute left-0 top-0 bottom-0 w-64 bg-atlasly-paper border-r border-atlasly-line">
            {sidebar}
          </aside>
        </div>
      ) : null}

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="md:hidden flex items-center gap-3 px-4 py-3 border-b border-atlasly-line bg-atlasly-paper">
          <button type="button" onClick={() => setMobileOpen(true)} aria-label="Open navigation menu">
            <Menu className="h-5 w-5 text-atlasly-muted" />
          </button>
          <span className="font-semibold text-atlasly-ink text-sm">Atlasly</span>
          <button type="button" className="ml-auto" aria-label="Atlasly help">
            <HelpCircle className="h-5 w-5 text-atlasly-muted" />
          </button>
        </header>

        <main className="flex-1 overflow-y-auto p-6 md:p-8 pb-24">
          <Outlet />
        </main>
      </div>

      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-atlasly-paper border-t border-atlasly-line flex">
        {[
          { to: '/', icon: LayoutDashboard, label: 'Home', exact: true },
          { to: '/letters', icon: FileText, label: 'Letters' },
          { to: '/tasks', icon: CheckSquare, label: 'Tasks' },
          { to: '/permits', icon: Building2, label: 'Permits' },
        ].map(({ to, icon: Icon, label, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) => cn(
              'flex-1 flex flex-col items-center py-2 gap-0.5 text-[10px] font-medium',
              isActive ? 'text-atlasly-teal' : 'text-atlasly-muted',
            )}
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {mobileOpen ? (
        <button type="button" className="fixed top-4 left-64 z-50 md:hidden text-white" onClick={() => setMobileOpen(false)} aria-label="Close navigation menu">
          <X className="h-5 w-5" />
        </button>
      ) : null}

      {isDemo ? <DemoToolbar onRoleChange={handleRoleSwitch} currentRole={role} /> : null}
    </div>
  )
}
