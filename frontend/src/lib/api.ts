const BASE = ''
const STORED_TOKEN_KEY = 'atlasly_session_token'

export class ApiError extends Error {
  status: number
  code?: string
  details?: unknown

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export interface SessionRecord {
  token: string
  role: string
  expires_at?: string
}

export interface RuntimeInfo {
  deployment_tier?: string
  demo_routes_enabled?: boolean
}

function getToken(): string | null {
  return localStorage.getItem(STORED_TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(STORED_TOKEN_KEY, token)
    return
  }
  localStorage.removeItem(STORED_TOKEN_KEY)
}

async function parseError(res: Response): Promise<ApiError> {
  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    const payload = await res.json().catch(() => ({})) as Record<string, unknown>
    const nested = payload.error as Record<string, unknown> | string | undefined
    if (nested && typeof nested === 'object') {
      const message = String(nested.message ?? nested.code ?? `HTTP ${res.status}`)
      return new ApiError(message, res.status, nested.code ? String(nested.code) : undefined, payload)
    }
    if (typeof nested === 'string') {
      return new ApiError(nested, res.status, undefined, payload)
    }
    return new ApiError(String(payload.message ?? `HTTP ${res.status}`), res.status, undefined, payload)
  }
  const text = await res.text().catch(() => '')
  return new ApiError(text || `HTTP ${res.status}`, res.status)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const hasBody = options.body !== undefined && options.body !== null
  const headers: HeadersInit = {
    ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    throw await parseError(res)
  }

  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return res.json() as Promise<T>
  }
  return res.text() as unknown as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
}

export async function bootstrap(): Promise<{ token: string; sessions: SessionRecord[]; runtime?: RuntimeInfo }> {
  const data = await api.post<{ session?: SessionRecord; sessions?: SessionRecord[]; token?: string }>('/api/bootstrap', {
    org_name: 'My Organization',
    user_name: 'owner',
    email: 'owner@atlasly.app',
  }) as { session?: SessionRecord; sessions?: SessionRecord[]; token?: string; runtime?: RuntimeInfo }
  const token = data?.session?.token ?? (data as Record<string, string>)?.token ?? ''
  if (token) setToken(token)
  return { token, sessions: data.sessions ?? [], runtime: data.runtime }
}

export function getStoredToken(): string | null {
  return getToken()
}

export async function fetchSessions(): Promise<{ sessions: SessionRecord[]; runtime?: RuntimeInfo }> {
  const data = await api.get<{ sessions?: SessionRecord[]; runtime?: RuntimeInfo }>('/api/sessions')
  return { sessions: data.sessions ?? [], runtime: data.runtime }
}
