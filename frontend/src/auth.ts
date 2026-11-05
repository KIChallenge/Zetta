export interface User {
  id: string | number
  email: string
  display_name: string
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const KEY = 'access_token'
const UNREACHABLE = 'Der Server ist gerade nicht erreichbar. Bitte versuchen Sie es später noch einmal.'

// shortcut: JWT in localStorage is readable by any script on the page; move to an httpOnly cookie before production.
export const getToken = () => localStorage.getItem(KEY)
export const clearToken = () => localStorage.removeItem(KEY)

async function request<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, UNREACHABLE)
  }
  // The dev proxy (or any gateway) answers 502-504 when the backend is down.
  if (res.status >= 502 && res.status <= 504) throw new ApiError(res.status, UNREACHABLE)
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : 'Das hat leider nicht geklappt. Bitte versuchen Sie es noch einmal.')
  }
  return body as T
}

export async function authenticate(path: '/auth/login' | '/auth/register', payload: Record<string, string>): Promise<User> {
  const { access_token, user } = await request<{ access_token: string; user: User }>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  localStorage.setItem(KEY, access_token)
  return user
}

export const me = () => request<User>('/me', { headers: { Authorization: `Bearer ${getToken()}` } })
