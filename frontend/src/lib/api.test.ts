import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, bootstrap, fetchSessions, getStoredToken, setToken } from '@/lib/api'

describe('api helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('bootstrap stores the owner token from the bootstrap payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        session: { token: 'owner-token', role: 'owner' },
        sessions: [{ token: 'owner-token', role: 'owner' }],
      }),
    }))

    const result = await bootstrap()
    expect(result.token).toBe('owner-token')
    expect(getStoredToken()).toBe('owner-token')
  })

  it('fetchSessions returns session rows from the backend', async () => {
    setToken('owner-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({
        sessions: [
          { token: 'owner-token', role: 'owner' },
          { token: 'admin-token', role: 'admin' },
        ],
      }),
    }))

    const sessions = await fetchSessions()
    expect(sessions).toHaveLength(2)
    expect(sessions[1].role).toBe('admin')
  })

  it('throws ApiError with nested error message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ error: { code: 'forbidden', message: 'role not allowed for route' } }),
    }))

    await expect(fetchSessions()).rejects.toMatchObject({
      name: 'ApiError',
      message: 'role not allowed for route',
      status: 403,
      code: 'forbidden',
    } satisfies Partial<ApiError>)
  })
})
