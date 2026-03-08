/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { bootstrap, fetchSessions, getStoredToken, setToken, type SessionRecord } from '@/lib/api'
import type { Role } from '@/lib/constants'

interface AuthState {
  token: string | null
  role: Role
  ready: boolean
  sessions: SessionRecord[]
}

interface AuthContextValue extends AuthState {
  switchRole: (role: Role) => Promise<void>
  refreshSessions: () => Promise<void>
}

const STORED_ROLE_KEY = 'atlasly_role'
const AuthContext = createContext<AuthContextValue | null>(null)

function normalizeRole(raw: string | null): Role {
  if (raw === 'owner' || raw === 'admin' || raw === 'pm' || raw === 'reviewer' || raw === 'subcontractor') {
    return raw
  }
  return 'owner'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [state, setState] = useState<AuthState>({
    token: getStoredToken(),
    role: normalizeRole(localStorage.getItem(STORED_ROLE_KEY)),
    ready: false,
    sessions: [],
  })

  const refreshSessions = useCallback(async () => {
    const sessions = await fetchSessions()
    setState((prev) => ({ ...prev, sessions }))
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const boot = await bootstrap()
        if (cancelled) return
        const storedRole = normalizeRole(localStorage.getItem(STORED_ROLE_KEY))
        const matching = boot.sessions.find((session) => session.role === storedRole)
        const nextToken = matching?.token ?? boot.token
        setToken(nextToken)
        setState({
          token: nextToken,
          role: matching?.role ? normalizeRole(matching.role) : storedRole,
          ready: true,
          sessions: boot.sessions,
        })
      } catch {
        if (!cancelled) {
          setState((prev) => ({ ...prev, ready: true }))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const switchRole = useCallback(async (role: Role) => {
    const sessions = state.sessions.length > 0 ? state.sessions : await fetchSessions()
    const nextSession = sessions.find((session) => session.role === role)
    if (!nextSession) {
      throw new Error(`No active session for role ${role}`)
    }
    localStorage.setItem(STORED_ROLE_KEY, role)
    setToken(nextSession.token)
    queryClient.clear()
    setState((prev) => ({
      ...prev,
      token: nextSession.token,
      role,
      sessions,
    }))
  }, [queryClient, state.sessions])

  const value = useMemo<AuthContextValue>(() => ({
    ...state,
    switchRole,
    refreshSessions,
  }), [refreshSessions, state, switchRole])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
