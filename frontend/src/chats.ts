import { ApiError, GENERIC, getToken, request, respond, UNREACHABLE } from './auth'

export interface Chat {
  id: string | number
  title: string
  created_at: string
  updated_at: string
  status?: string | null // e.g. "3 offene Schritte", "Frage offen"
}

export interface Chip {
  value: string
  label: string
}

export interface Channel {
  type: 'phone' | 'email' | 'web' | 'visit'
  value: string
  label: string | null
  href?: string
  hours?: string
  reachable?: { open: boolean; text: string }
  source_url: string | null
}

export interface Institution {
  name: string
  address: string | null
  channels: Channel[]
  source_url: string
}

export interface QuestionPayload { fact_key: string; chips: Chip[]; why: string; multi?: boolean }
export interface AnswerPayload { fact_key: string; value: string | string[] }
export interface PlanPayload { version: number }
export interface CardPayload { card: 'boundary' | 'out_of_scope' | 'general'; title: string; contacts: Institution[] }
export interface ConfirmPayload { items: { recommendation: string; label: string; quote: string }[] }
export type Payload = QuestionPayload | AnswerPayload | PlanPayload | CardPayload | ConfirmPayload

export interface Message {
  id: string | number
  role: 'user' | 'assistant'
  kind: 'text' | 'answer' | 'document' | 'question' | 'confirm' | 'plan' | 'card'
  text: string
  payload: Payload | null
  created_at: string
}

export interface Fact {
  key: string
  label: string
  value: string | string[]
  value_label: string
  source: 'profile' | 'user_text' | 'chip'
  chips: Chip[]
}

export interface Doc {
  id: string
  title: string
  where_to_get: string
  notes: string | null
}

export interface Script {
  opening?: string
  points?: { covers: string; text: string }[]
  closing?: string
  subject?: string
  body?: string
  have_ready: { label: string; value: string | null }[]
  source: 'llm' | 'fallback'
}

export interface Doctor {
  id: string
  name: string
  address: string
  contract: string
  warning: string | null // shown in red: the practice may not take the user's insurance
  warning_source: string | null
  contact: Channel
}

export interface Step {
  id: string
  service: string
  services?: string[] // a merged checklist
  type: 'call' | 'email' | 'form' | 'info' | 'wait' | 'documents' | 'upload' | 'book'
  title: string
  why: string
  after: string[]
  text: string | null
  status: 'blocked' | 'available' | 'done' | 'skipped'
  outcome: string | null
  note: string | null
  checks: string[]
  updated_at: string | null
  outcomes: { id: string; label: string }[]
  institution?: { id: string | null; name: string; address: string | null } // id null: the user's own doctor
  contact?: Channel
  doctors?: Doctor[] // practices to choose from, instead of one contact
  doctors_source?: { url: string; scraped_at: string }
  more?: Channel // a search for further practices
  form?: { title: string; url: string; online_url: string | null }
  documents?: Doc[]
  script?: Script
}

export interface Service {
  id: string
  title: string
  summary: string
  eligibility: 'likely' | 'possible'
  criteria: { text: string; state: 'met' | 'not_met' | 'unknown' }[]
  checked_by: string[]
  responsible: string | null
  quotes: string[] // from the user's confirmed letter
  responsible_note: string | null
  responsible_source: string | null
  source_url: string
}

export interface Plan {
  version: number
  services: Service[]
  dropped: { id: string; title: string; reason: string }[]
  steps: Step[]
  status: string
}

export interface StepUpdate {
  status?: 'done' | 'skipped' | 'open'
  outcome?: string
  note?: string
  checks?: string[]
}

export type ReplyEvent =
  | { event: 'message'; data: Message }
  | { event: 'facts'; data: Fact[] }
  | { event: 'plan'; data: Plan }
  | { event: 'title'; data: Chat }
  | { event: 'done'; data: Message }
  | { event: 'error'; data: { status: number; detail: string } }

const init = (method: string, body?: object, signal?: AbortSignal): RequestInit => ({
  method,
  headers: { Authorization: `Bearer ${getToken()}`, ...(body && { 'Content-Type': 'application/json' }) },
  body: body && JSON.stringify(body),
  signal,
})
export const api = <T>(path: string, method = 'GET', body?: object) => request<T>(path, init(method, body))

// The id can come from the URL hash, so it is encoded before it becomes part of a path.
const at = (id: string | number) => `/chats/${encodeURIComponent(id)}`

export const listChats = () => api<Chat[]>('/chats')
export const createChat = (title: string) => api<Chat>('/chats', 'POST', { title })
export const renameChat = (id: string | number, title: string) => api<Chat>(at(id), 'PATCH', { title })
export const deleteChat = (id: string | number) => api<null>(at(id), 'DELETE')
export const listMessages = (id: string | number) => api<Message[]>(`${at(id)}/messages`)
export const getState = (id: string | number) => api<{ facts: Fact[]; plan: Plan | null }>(`${at(id)}/state`)
// The raw PDF as the body; the server keeps only the recommendations the user then confirms.
export const uploadDocument = async (id: string | number, file: File) => {
  const res = await respond(`${at(id)}/documents`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}`, 'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(file.name) },
    body: file,
  })
  return (await res.json()) as Message[]
}
export const updateStep = (id: string | number, step: string, body: StepUpdate) =>
  api<Plan>(`${at(id)}/steps/${encodeURIComponent(step)}`, 'PATCH', body)

/**
 * Sends a message (or, with `answer`, a chip answer) and calls `on` for each Server-Sent Event of the reply.
 * fetch instead of EventSource, which can neither POST nor send the token. Resolves when the stream ends.
 */
export async function sendMessage(
  id: string | number,
  text: string,
  signal: AbortSignal,
  on: (e: ReplyEvent) => void,
  answer?: { fact_key: string; value: string | string[] },
) {
  const res = await respond(
    `${at(id)}/${answer ? 'answers' : 'messages'}`,
    init('POST', answer ?? { text }, signal),
  )
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
