import { ApiError, GENERIC, getToken, request, respond, UNREACHABLE } from './auth'

export interface Chat {
  id: string | number
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string | number
  role: 'user' | 'assistant'
  text: string
  created_at: string
}

export type ReplyEvent =
  | { event: 'message'; data: Message }
  | { event: 'delta'; data: { text: string } }
  | { event: 'title'; data: Chat }
  | { event: 'done'; data: Message }
  | { event: 'error'; data: { status: number; detail: string } }

const init = (method: string, body?: object, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { Authorization: `Bearer ${getToken()}`, ...(body && { 'Content-Type': 'application/json' }) },
  body: body && JSON.stringify(body),
  signal,
})
const api = <T>(path: string, method = 'GET', body?: object) => request<T>(path, init(method, body))

// The id can come from the URL hash, so it is encoded before it becomes part of a path.
const at = (id: string | number) => `/chats/${encodeURIComponent(id)}`

export const listChats = () => api<Chat[]>('/chats')
export const createChat = (title: string) => api<Chat>('/chats', 'POST', { title })
export const renameChat = (id: string | number, title: string) => api<Chat>(at(id), 'PATCH', { title })
export const deleteChat = (id: string | number) => api<null>(at(id), 'DELETE')
export const listMessages = (id: string | number) => api<Message[]>(`${at(id)}/messages`)
/**
 * Sends a message and calls `on` for each Server-Sent Event of the streamed reply.
 * fetch instead of EventSource, which can neither POST nor send the token. Resolves when the stream ends.
 */
export async function sendMessage(id: string | number, text: string, signal: AbortSignal, on: (e: ReplyEvent) => void) {
  const res = await respond(`${at(id)}/messages`, init('POST', { text }, signal))
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buf += value
    let end
    while ((end = buf.indexOf('\n\n')) >= 0) {
      // Our server sends one `event:` and one single-line JSON `data:` per event; keep-alive pings have neither.
      const block = buf.slice(0, end)
      buf = buf.slice(end + 2)
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = /^data: (.*)$/m.exec(block)?.[1]
      if (event && data) on({ event, data: JSON.parse(data) } as ReplyEvent)
    }
  }
}

export const NOT_FOUND = 'Gespräch nicht gefunden.'

// Backend detail texts are English, so every error is shown with our own German wording.
export function say(e: unknown, invalid = GENERIC) {
  const status = e instanceof ApiError ? e.status : 0
  if (status === 404) return NOT_FOUND
  if (status === 422) return invalid
  return (e as Error).message === UNREACHABLE ? UNREACHABLE : GENERIC
}

export function titleFrom(text: string, max = 48) {
  const t = text.trim().replace(/\s+/g, ' ')
  if (t.length <= max) return t
  const cut = t.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return (space > max / 2 ? cut.slice(0, space) : cut).trimEnd() + '…'
}

const day = new Intl.DateTimeFormat('de-AT', { day: 'numeric', month: 'short', year: 'numeric' })
const time = new Intl.DateTimeFormat('de-AT', { hour: '2-digit', minute: '2-digit' })

export function when(iso: string) {
  // A timestamp without offset is UTC by contract; without the Z the browser would read it as local time.
  const d = new Date(/(z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : iso + 'Z')
  return `${d.toDateString() === new Date().toDateString() ? 'Heute' : day.format(d)}, ${time.format(d)} Uhr`
}
