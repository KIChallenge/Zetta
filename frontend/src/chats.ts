import { ApiError, GENERIC, HEADERS, request, respond, TOO_MANY, UNREACHABLE } from './auth'
import { intlLocale, k, t, translating } from './i18n'

export interface Chat {
  id: string | number
  title: string
  created_at: string
  updated_at: string
  status?: string | null // e.g. "3 offene Schritte", "Frage offen"
  next?: NextUp | null
}

/** What a chat waits for: the open question, the next step to do, or that it waits or is done. */
export interface NextUp {
  kind: 'question' | 'step' | 'waiting' | 'done'
  text?: string | null
  type?: string | null
  institution?: string | null
  reachable?: { open: boolean; text: string } | null
  open_steps?: number
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

export interface QuestionPayload { fact_key: string; chips: Chip[]; why: string; multi?: boolean; note?: string }
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
  // The corpus script with its placeholders: when translating it is shown instead, so both versions say the same.
  plain?: null | {
    template: { opening?: string; points?: { covers: string; text: string }[]; closing?: string; subject?: string; body?: string }
    slots: Record<string, { value: string | null; gap: string }>
  }
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
  // prefill: the form can be downloaded filled in with these details (labels); ask: the ones still missing.
  // wizard: the whole form is filled in with FormWizard; how many of its required answers are there.
  form?: { id?: string; title: string; url: string; online_url: string | null; prefill?: Prefill; wizard?: Progress }
  documents?: Doc[]
  script?: Script
}

export interface Progress {
  done: number
  total: number
}

/** One question of a form wizard (backend: forms.wizard). The label is the German form's own wording. */
export interface WizardQuestion {
  id: string
  label: string
  kind: 'text' | 'multiline' | 'date' | 'number' | 'choice' | 'yes_no' | 'checkbox'
  options: Record<string, string>
  help: string | null
  source_url: string | null
  required: boolean
  suggest: boolean // the LLM may draft it
  max: number | null // characters the paper form has room for
  detail: string | null // a person's detail, e.g. "svnr": checked and formatted like in the settings
  when: Condition[] // shown when one holds; none: always
  value: string
  source: 'answer' | 'profile' | 'kept' | 'fact' | 'constant' | null
  source_label: string | null // for a chat fact: its value, e.g. "Pension von der PV"
}

/** Fact or question id -> the values it must have (one of them), or {not: [...]}. */
export type Condition = Record<string, string[] | { not: string[] }>

export interface WizardSection {
  id: string
  title: string
  heading: string | null
  page: number | null
  point: number | null
  questions: WizardQuestion[]
}

export interface Finding {
  kind: 'missing' | 'check'
  question?: string
  section?: string
  label?: string
  text?: string
}

export interface Wizard {
  form: { id: string; title: string; url: string; online_url: string | null }
  subject: string | null // e.g. "Mutter"
  submit_to: { name: string; address: string | null } | null
  sections: WizardSection[]
  manual: { label: string; page: number | null; point: number | null }[] // filled in by hand on paper
  facts: Record<string, string | string[]> // the chat facts the questions' conditions look at
  findings: Finding[]
  progress: Progress
}

export interface Hint {
  question: string
  section: string
  text: string
}

export type HelpBody = { kind: 'explain' | 'suggest'; question: string } | { kind: 'ask'; text: string } | { kind: 'check' }
export interface HelpReply {
  text?: string
  hints?: Hint[]
  refused?: boolean // a medical question: not sent to the LLM
}

export interface Prefill {
  filled: string[]
  ask: Ask[]
  done: number // fields with the person's details that are filled
  total: number
}

/** One detail of a person, as asked for: `fields` are keys of PersonData (backend/schemas.py), `values` the known ones. */
export interface Entry {
  who?: string
  entry: string
  label: string
  fields: string[]
  values: Record<string, string>
  choices: Record<string, Record<string, string>>
}

/** A detail a form still needs, asked for on its card: the user's own or the subject's. */
export interface Ask extends Entry {
  who: 'user' | 'subject'
}

export interface FormBody {
  user: Record<string, string>
  subject: Record<string, string>
  remember: boolean
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
  headers: { ...HEADERS, ...(body && { 'Content-Type': 'application/json' }) },
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
    headers: { ...HEADERS, 'Content-Type': 'application/pdf', 'X-Filename': encodeURIComponent(file.name) },
    body: file,
  })
  return (await res.json()) as Message[]
}
export const updateStep = (id: string | number, step: string, body: StepUpdate) =>
  api<Plan>(`${at(id)}/steps/${encodeURIComponent(step)}`, 'PATCH', body)
const formAt = (id: string | number, step: string) => `${at(id)}/steps/${encodeURIComponent(step)}/form`
export const getWizard = (id: string | number, step: string) => api<Wizard>(`${formAt(id, step)}/wizard`)
export const saveAnswers = (id: string | number, step: string, answers: Record<string, string>) =>
  api<Wizard>(`${formAt(id, step)}/answers`, 'PUT', { answers })
// The optional LLM layer: 503 when it is not available. The wizard works without it.
export const formHelp = (id: string | number, step: string, body: HelpBody) =>
  api<HelpReply>(`${formAt(id, step)}/help`, 'POST', body)

// The step's form filled in with the user's details. Fetched, so a failed download shows our error message.
// With `body`, also with the details just typed into its card.
export async function downloadForm(id: string | number, step: string, body?: FormBody) {
  const res = await respond(formAt(id, step), body ? init('POST', body) : init('GET'))
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'Antrag.pdf'
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Sends a message (or, with `answer`, a chip answer) and calls `on` for each Server-Sent Event of the reply.
 * fetch instead of EventSource, which cannot POST. Resolves when the stream ends.
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

export const NOT_FOUND = k('Gespräch nicht gefunden.')

// Backend detail texts are English, so every error is shown with our own wording. Show the result with t().
export function say(e: unknown, invalid = GENERIC) {
  const status = e instanceof ApiError ? e.status : 0
  if (status === 404) return NOT_FOUND
  if (status === 422) return invalid
  if (status === 429) return TOO_MANY
  return (e as Error).message === UNREACHABLE ? UNREACHABLE : GENERIC
}

export function titleFrom(text: string, max = 48) {
  const t = text.trim().replace(/\s+/g, ' ')
  if (t.length <= max) return t
  const cut = t.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return (space > max / 2 ? cut.slice(0, space) : cut).trimEnd() + '…'
}

export function when(iso: string) {
  // A timestamp without offset is UTC by contract; without the Z the browser would read it as local time.
  const d = new Date(/(z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : iso + 'Z')
  const day = new Intl.DateTimeFormat(intlLocale.value, { day: 'numeric', month: 'short', year: 'numeric' })
  const time = new Intl.DateTimeFormat(intlLocale.value, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
  const date = d.toDateString() === new Date().toDateString() ? t('Heute') : day.format(d)
  return `${date}, ${time.format(d)}${translating.value ? '' : ' Uhr'}`
}
