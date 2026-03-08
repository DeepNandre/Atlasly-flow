import { useEffect, useState } from 'react'
import { bootstrap, setToken } from '@/lib/api'
import type { Role } from '@/lib/constants'

interface AuthState {
  token: string | null
  role: Role
  orgId: string | null
  userId: string | null
  ready: boolean
}

const STORED_ROLE_KEY = 'atlasly_role'
const STORED_ORG_KEY = 'atlasly_org_id'
const STORED_USER_KEY = 'atlasly_user_id'
const STORED_TOKEN_KEY = 'atlasly_session_token'

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>({
    token: localStorage.getItem(STORED_TOKEN_KEY),
    role: (localStorage.getItem(STORED_ROLE_KEY) as Role) ?? 'owner',
    orgId: localStorage.getItem(STORED_ORG_KEY),
    userId: localStorage.getItem(STORED_USER_KEY),
    // Always start not-ready so we re-bootstrap on every fresh server start.
    // Bootstrap is idempotent: if workspace exists, it just re-seeds tokens.
    ready: false,
  })

  useEffect(() => {
    // Always re-bootstrap on mount — gets fresh tokens even after server restart.
    bootstrap()
      .then((token) => {
        setAuth((prev) => ({ ...prev, token, ready: true }))
      })
      .catch(() => {
        // If bootstrap itself fails, still render the app (shows error states on pages).
        setAuth((prev) => ({ ...prev, ready: true }))
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const switchRole = (role: Role) => {
    localStorage.setItem(STORED_ROLE_KEY, role)
    setAuth((prev) => ({ ...prev, role }))
  }

  const storeBootstrapData = (data: {
    token?: string
    org_id?: string
    user_id?: string
    role?: Role
  }) => {
    if (data.token) {
      setToken(data.token)
      localStorage.setItem(STORED_TOKEN_KEY, data.token)
    }
    if (data.org_id) localStorage.setItem(STORED_ORG_KEY, data.org_id)
    if (data.user_id) localStorage.setItem(STORED_USER_KEY, data.user_id)
    if (data.role) localStorage.setItem(STORED_ROLE_KEY, data.role)
    setAuth({
      token: data.token ?? auth.token,
      role: data.role ?? auth.role,
      orgId: data.org_id ?? auth.orgId,
      userId: data.user_id ?? auth.userId,
      ready: true,
    })
  }

  return { ...auth, switchRole, storeBootstrapData }
}
