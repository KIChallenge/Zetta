import { k } from './i18n'

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

export const UNREACHABLE = k('Der Server ist gerade nicht erreichbar. Bitte versuchen Sie es später noch einmal.')
export const GENERIC = k('Das hat leider nicht geklappt. Bitte versuchen Sie es noch einmal.')
export const TOO_MANY = k('Das waren gerade sehr viele Versuche. Bitte warten Sie ein paar Minuten.')

// The session is an httpOnly cookie that the browser sends by itself: no script can read it. The server only
// accepts it for changes together with this header, which another site cannot send.
export const HEADERS = { 'X-Requested-With': 'fetch' }
try {
  localStorage.removeItem('access_token') // where older versions kept the token
} catch {
  // Storage blocked: nothing was stored there either.
}

/** fetch that throws an ApiError unless the response is ok. */
export async function respond(path: string, init: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, UNREACHABLE)
  }
  // The dev proxy (or any gateway) answers 502-504 when the backend is down.
  if (res.status >= 502 && res.status <= 504) throw new ApiError(res.status, UNREACHABLE)
  if (!res.ok) {
    const detail = (await res.json().catch(() => null))?.detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : GENERIC)
  }
  return res
}

export async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await respond(path, init)
  return (await res.json().catch(() => null)) as T
}

export async function authenticate(path: '/auth/login' | '/auth/register', payload: Record<string, string>): Promise<User> {
  const { user } = await request<{ user: User }>(path, {
    method: 'POST',
    headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return user
}

export const me = () => request<User>('/me', { headers: HEADERS })
// Ends the session on every device. A failure (already signed out, server down) changes nothing for the user.
export const logout = () => respond('/auth/logout', { method: 'POST', headers: HEADERS }).catch(() => {})
