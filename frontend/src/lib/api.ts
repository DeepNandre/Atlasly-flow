const BASE = ''

function getToken(): string | null {
  return localStorage.getItem('atlasly_session_token')
}

function setToken(token: string): void {
  localStorage.setItem('atlasly_session_token', token)
}

export { setToken }

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers ?? {}),
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
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

export async function bootstrap(): Promise<string> {
  const data = await api.post<{ session?: { token?: string }; token?: string }>(
    '/api/bootstrap',
    {
      org_name: 'My Organization',
      user_name: 'owner',
      email: 'owner@atlasly.app',
    },
  )
  const token =
    data?.session?.token ?? (data as Record<string, string>)?.token ?? ''
  if (token) setToken(token)
  return token
}
