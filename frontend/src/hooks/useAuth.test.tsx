import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '@/hooks/useAuth'

function Probe() {
  const auth = useAuth()

  useEffect(() => {
    if (auth.ready && auth.role === 'owner') {
      void auth.switchRole('admin')
    }
  }, [auth])

  return <div>{auth.ready ? auth.role : 'loading'}</div>
}

describe('AuthProvider', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('bootstraps sessions and switches roles by swapping the stored token', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/bootstrap')) {
        return {
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            session: { token: 'owner-token', role: 'owner' },
            sessions: [
              { token: 'owner-token', role: 'owner' },
              { token: 'admin-token', role: 'admin' },
            ],
          }),
        }
      }
      if (url.endsWith('/api/sessions')) {
        return {
          ok: true,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({
            sessions: [
              { token: 'owner-token', role: 'owner' },
              { token: 'admin-token', role: 'admin' },
            ],
          }),
        }
      }
      throw new Error(`Unhandled URL ${url}`)
    }))

    const queryClient = new QueryClient()
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument())
    expect(localStorage.getItem('atlasly_session_token')).toBe('admin-token')
    expect(localStorage.getItem('atlasly_role')).toBe('admin')
  })
})
