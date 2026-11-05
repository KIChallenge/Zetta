<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import { ApiError, UNREACHABLE, type User } from '../auth'
import {
  createChat, deleteChat, getState, listChats, listMessages, NOT_FOUND, renameChat, say, sendMessage, titleFrom,
  updateStep, uploadDocument, when,
  type AnswerPayload, type CardPayload, type Chat, type Chip, type ConfirmPayload, type Fact, type Message, type Plan,
  type PlanPayload,
  type QuestionPayload, type StepUpdate,
} from '../chats'
import { toHtml } from '../markdown'
import { getProfile, type Profile } from '../profile'
import DocumentConfirm from './DocumentConfirm.vue'
import FactChips from './FactChips.vue'
import NoticeCard from './NoticeCard.vue'
import PlanView from './PlanView.vue'
import ProfileCard from './ProfileCard.vue'
import QuestionCard from './QuestionCard.vue'
import SettingsPage from './SettingsPage.vue'

type Bubble = Message & {
  key?: number
  state?: 'sending' | 'delivered' | 'failed'
  error?: string
  html?: string // older free-text replies: sanitized Markdown
  pending?: boolean // assistant only: the reply is being prepared
}

defineProps<{ user: User }>()
const emit = defineEmits<{ expired: []; deleted: [] }>()

const LIST = 'gespraeche'
const SETTINGS = 'einstellungen'
const STATE = { sending: 'Wird gesendet …', delivered: 'Zugestellt', failed: 'Nicht zugestellt' }
const NO_REPLY = 'Die Antwort konnte gerade nicht erstellt werden.'

const hash = ref(location.hash.slice(1))
const activeId = computed(() => (hash.value && hash.value !== LIST && hash.value !== SETTINGS ? decodeURIComponent(hash.value) : null))
const chats = ref<Chat[]>([])
const active = computed(() => chats.value.find((c) => String(c.id) === activeId.value))
const listLoaded = ref(false)
const listErr = ref('')
const messages = ref<Bubble[]>([])
const loading = ref(false)
const loadErr = ref('')
const notice = ref('')
const draft = ref('')
const draftErr = ref('')
const busy = ref(false)
const optsOpen = ref<string | null>(null)
const scroller = ref<HTMLElement>()
const renameDlg = ref<HTMLDialogElement>()
const deleteDlg = ref<HTMLDialogElement>()
const rnInput = ref<HTMLInputElement>()
const target = ref<Chat | null>(null)
const newTitle = ref('')
const dlgErr = ref('')
const run = shallowRef<{ chat: string; ctrl: AbortController } | null>(null) // the reply being requested
const announce = ref('')
const facts = ref<Fact[]>([]) // the "Verstanden" chips of the open chat
const plan = ref<Plan | null>(null) // its latest plan, with current step states
const planErr = ref('')
const profile = ref<Profile | null>(null) // for the "Das weiß der Lotse" card; SettingsPage reports saves
const profileFailed = ref(false)
let seq = 0
let preset: string | null = null // a chat opened right after creating it: its messages are already local
let pendingFocus = ''

// Every API error goes through here, so an expired session always ends at the login screen.
function fail(e: unknown, invalid?: string) {
  if (e instanceof ApiError && e.status === 401) emit('expired')
  return say(e, invalid)
}

const focus = (id: string) => nextTick(() => document.getElementById(id)?.focus())
const scrollDown = () => nextTick(() => scroller.value?.scrollTo({ top: scroller.value.scrollHeight }))
// Measured before an update: a new reply only scrolls along if the user has not scrolled up to read.
const nearBottom = (el = scroller.value) => !!el && el.scrollHeight - el.scrollTop - el.clientHeight < 80
const put = (c: Chat) => (chats.value = [c, ...chats.value.filter((x) => x.id !== c.id)])
const drop = (b: Bubble) => {
  const i = messages.value.indexOf(b)
  if (i >= 0) messages.value.splice(i, 1)
}
const withHtml = (m: Message): Bubble => (m.role === 'assistant' && m.kind === 'text' ? { ...m, html: toHtml(m.text) } : m)
const q = (m: Message) => m.payload as QuestionPayload
const card = (m: Message) => m.payload as CardPayload
// Only the plan of the latest version is interactive; older plan messages say they were replaced.
const isCurrent = (m: Message) => !!plan.value && (m.payload as PlanPayload).version === plan.value.version
// The facts sit above the latest reply if it is a plan or card, so a wrong fact can be fixed where the user is
// looking. Above a question they would only repeat the answers just given.
const anchor = computed(() => [...messages.value].reverse().find((m) => m.role === 'assistant' && !m.pending))
const lastMsg = computed(() => messages.value.at(-1))
function setStatus(id: string, status: string | null) {
  const c = chats.value.find((x) => String(x.id) === id)
  if (c) c.status = status
}

function route() {
  hash.value = location.hash.slice(1)
  optsOpen.value = null
  focus(pendingFocus || (hash.value === LIST ? 'side-h' : 'view-h'))
  pendingFocus = ''
}
function go(h: string, focusId = '', replace = false) {
  pendingFocus = focusId
  if (replace) history.replaceState(null, '', h ? `#${h}` : location.pathname + location.search)
  else if (hash.value !== h) return void (location.hash = h) // hashchange calls route()
  route()
}
onMounted(() => addEventListener('hashchange', route))
onUnmounted(() => {
  removeEventListener('hashchange', route)
  run.value?.ctrl.abort()
})

async function loadList() {
  listErr.value = ''
  try {
    chats.value = await listChats()
  } catch (e) {
    listErr.value = fail(e)
  }
  listLoaded.value = true
}
loadList()
getProfile()
  .then((p) => (profile.value = p))
  .catch((e) => {
    fail(e)
    profileFailed.value = true
  })

function profileSaved(p: Profile) {
  profile.value = p
  profileFailed.value = false
}

watch(activeId, async (id, _, onCleanup) => {
  let stale = false
  onCleanup(() => (stale = true))
  // Leaving a chat stops its reply; the server keeps what was written so far.
  if (run.value && run.value.chat !== id) run.value.ctrl.abort()
  loadErr.value = draftErr.value = planErr.value = ''
  loading.value = false
  if (id) notice.value = ''
  if (id && id === preset) return void (preset = null)
  messages.value = []
  facts.value = []
  plan.value = null
  if (!id) return
  loading.value = true
  try {
    const [list, state] = await Promise.all([listMessages(id), getState(id)])
    if (stale) return
    messages.value = list.map(withHtml)
    facts.value = state.facts
    plan.value = state.plan
  } catch (e) {
    if (stale) return
    const msg = fail(e)
    if (msg !== NOT_FOUND) loadErr.value = msg
    else {
      notice.value = msg
      go('', 'view-h', true)
    }
  } finally {
    if (!stale) loading.value = false
  }
  // Only after loading is cleared: the list is not rendered while the loading line shows.
  scrollDown()
}, { immediate: true })

function submit() {
  if (run.value) return // one reply at a time
  const text = draft.value.trim()
  draftErr.value = text ? '' : 'Bitte schreiben Sie zuerst Ihre Nachricht.'
  if (!text) return focus('q')
  notice.value = ''
  if (!activeId.value) return start(text)
  draft.value = ''
  deliver(activeId.value, text)
}

async function start(text: string) {
  if (busy.value) return
  busy.value = true
  let id = ''
  try {
    const c = await createChat(titleFrom(text))
    put(c)
    draft.value = ''
    messages.value = []
    id = preset = String(c.id)
    facts.value = []
    plan.value = null
    go(id, 'q')
  } catch (e) {
    draftErr.value = fail(e)
  }
  busy.value = false
  if (id) deliver(id, text)
}

function deliver(id: string, text: string, answer?: AnswerPayload) {
  const m: Bubble = reactive({
    key: ++seq, id: '', role: 'user' as const, kind: answer ? ('answer' as const) : ('text' as const), text,
    payload: answer ?? null, created_at: new Date().toISOString(),
  })
  messages.value.push(m)
  scrollDown()
  retry(id, m)
}

// A chip answer, or an edited fact: set directly, without the LLM.
function answer(key: string, chip: Chip, label = chip.label) {
  if (run.value || !activeId.value) return
  notice.value = ''
  deliver(activeId.value, label, { fact_key: key, value: chip.value })
}
const editFact = (f: Fact, chip: Chip) => answer(f.key, chip, `${f.label}: ${chip.label}`)
function answerMany(key: string, chips: Chip[]) {
  if (run.value || !activeId.value || !chips.length) return
  deliver(activeId.value, chips.map((c) => c.label).join(', '), { fact_key: key, value: chips.map((c) => c.value) })
}
function confirmLetter(values: string[], labels: string[]) {
  if (run.value || !activeId.value) return
  const label = labels.length ? 'Stimmt so' : 'Keine davon stimmt'
  deliver(activeId.value, label, { fact_key: 'documented_recommendations', value: values.length ? values : 'unknown' })
}

// A discharge letter (PDF with text). Photos are not supported yet.
const fileInput = ref<HTMLInputElement>()
const uploading = ref(false)
async function upload(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  let id = activeId.value
  if (!file || run.value || busy.value) return
  draftErr.value = ''
  uploading.value = true
  try {
    // From the start view the letter is the first message: open a new chat for it, as start() does for text.
    if (!id) {
      const c = await createChat('Entlassungsbrief')
      put(c)
      messages.value = []
      facts.value = []
      plan.value = null
      id = preset = String(c.id)
      go(id, 'q')
    }
    const added = await uploadDocument(id, file)
    if (activeId.value === id) messages.value.push(...added)
    scrollDown()
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 0
    draftErr.value =
      status === 415 ? 'Bitte laden Sie eine PDF-Datei hoch.'
      : status === 413 ? 'Die Datei ist zu groß (höchstens 10 MB).'
      : status === 422 ? 'In dieser PDF ist kein Text lesbar. Fotos und Scans gehen noch nicht.'
      : fail(err)
  }
  uploading.value = false
}

async function retry(id: string, m: Bubble) {
  if (run.value) return
  const ctrl = new AbortController()
  run.value = { chat: id, ctrl }
  m.state = 'sending'
  announce.value = ''
  const r: Bubble = reactive({
    key: ++seq, id: '', role: 'assistant' as const, kind: 'text' as const, text: '', payload: null,
    created_at: new Date().toISOString(), pending: true,
  })
  let done = false
  try {
    const onEvent = (e: Parameters<Parameters<typeof sendMessage>[3]>[0]) => {
      if (e.event === 'message') {
        Object.assign(m, e.data, { state: 'delivered' })
        // Right after its question, and only if that question is still shown.
        const i = messages.value.indexOf(m)
        if (i >= 0) {
          const stick = nearBottom()
          messages.value.splice(i + 1, 0, r)
          if (stick) scrollDown()
        }
        const c = chats.value.find((x) => String(x.id) === id)
        if (c) put({ ...c, updated_at: e.data.created_at })
      } else if (e.event === 'facts') {
        if (activeId.value === id) facts.value = e.data
      } else if (e.event === 'plan') {
        if (activeId.value === id) plan.value = e.data
        planErr.value = ''
      } else if (e.event === 'title') {
        put(e.data)
      } else if (e.event === 'done') {
        Object.assign(r, e.data, { pending: false })
        done = true
        setStatus(id, plan.value?.status ?? (e.data.kind === 'question' ? 'Frage offen' : null))
      } else {
        throw new Error(e.data.detail)
      }
    }
    await sendMessage(id, m.text, ctrl.signal, onEvent, m.kind === 'answer' ? (m.payload as AnswerPayload) : undefined)
    // A stream that ends without "done" lost its connection.
    if (!done) throw new ApiError(0, UNREACHABLE)
    announce.value = r.kind === 'question' ? `Frage: ${r.text}` : 'Antwort fertig'
  } catch (e) {
    // Left the chat: the server keeps what it saved. Otherwise nothing was saved, so it can be sent again.
    if (!ctrl.signal.aborted) {
      m.state = 'failed'
      m.error = e instanceof ApiError ? fail(e, 'Die Nachricht darf höchstens 4000 Zeichen lang sein.') : NO_REPLY
    }
  } finally {
    if (r.pending) drop(r)
    run.value = null
  }
  // The user just asked or answered, so the reply is shown (after `run` is cleared: that brings the chips):
  // a plan from its start, anything else whole. A failed message grows by the retry button.
  if (done && r.kind === 'plan') nextTick(() => document.getElementById(`m-${r.key}`)?.scrollIntoView({ block: 'start' }))
  else if (done || (m.state === 'failed' && messages.value.at(-1) === m)) scrollDown()
}

async function patchStep(step: string, body: StepUpdate) {
  const id = activeId.value
  if (!id) return
  planErr.value = ''
  try {
    const next = await updateStep(id, step, body)
    if (activeId.value !== id) return
    plan.value = next
    setStatus(id, next.status)
  } catch (e) {
    planErr.value = fail(e)
  }
}
const toPlan = () => document.getElementById('plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' })

const toggle = (id: string) => (optsOpen.value = optsOpen.value === id ? null : id)

async function openRename(c: Chat) {
  target.value = c
  newTitle.value = c.title
  dlgErr.value = ''
  await nextTick()
  renameDlg.value?.showModal()
  rnInput.value?.select()
}

async function saveRename() {
  const c = target.value!
  const title = newTitle.value.trim()
  dlgErr.value = title ? '' : 'Bitte geben Sie einen Namen ein.'
  if (!title) return focus('rn-input')
  try {
    put(await renameChat(c.id, title))
    renameDlg.value?.close()
    optsOpen.value = null
    focus(`more-${c.id}`)
  } catch (e) {
    dlgErr.value = fail(e, 'Der Name darf höchstens 100 Zeichen lang sein.')
  }
}

function openDelete(c: Chat) {
  target.value = c
  dlgErr.value = ''
  deleteDlg.value?.showModal()
}

async function confirmDelete() {
  const c = target.value!
  try {
    await deleteChat(c.id)
  } catch (e) {
    // 404: someone already deleted it, which is what the user wanted.
    if (!(e instanceof ApiError && e.status === 404)) return void (dlgErr.value = fail(e))
  }
  chats.value = chats.value.filter((x) => x.id !== c.id)
  deleteDlg.value?.close()
  if (String(c.id) === activeId.value) go('', 'view-h')
  else focus('new-btn')
}
</script>

<template>
  <div class="shell" :data-pane="hash === LIST ? 'list' : 'main'">
    <nav class="side" aria-labelledby="side-h">
      <button id="new-btn" type="button" class="btn btn-primary btn-block" @click="go('', 'q')">
        <svg class="i" aria-hidden="true"><use href="#i-plus" /></svg>Neues Anliegen
      </button>
      <div class="side-h-row">
        <h2 id="side-h" class="caps" tabindex="-1">Ihre Gespräche</h2>
        <span v-if="chats.length" class="muted">{{ chats.length }}</span>
      </div>
      <template v-if="listErr">
        <p class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ listErr }}</span></p>
        <button type="button" class="btn btn-secondary" @click="loadList">Nochmal laden</button>
      </template>
      <ul v-else class="chats">
        <li v-for="c in chats" :key="c.id" class="ci" :class="{ on: String(c.id) === activeId }">
          <a class="ci-link" :href="`#${c.id}`" :aria-current="String(c.id) === activeId ? 'page' : undefined">
            <span class="ci-title">{{ c.title }}</span>
            <span v-if="c.status" class="pill ci-status" :data-tone="c.status === 'Erledigt' ? 'ready' : c.status.startsWith('Wartet') ? 'wait' : 'turn'">{{ c.status }}</span>
            <span class="ci-when"><span class="sr">Zuletzt geändert: </span>{{ when(c.updated_at) }}</span>
          </a>
          <button
            :id="`more-${c.id}`"
            type="button"
            class="ci-more"
            :aria-expanded="optsOpen === String(c.id)"
            :aria-controls="`opt-${c.id}`"
            title="Umbenennen oder löschen"
            @click="toggle(String(c.id))"
          >
            <svg class="i" aria-hidden="true"><use href="#i-more" /></svg><span class="sr">Optionen für „{{ c.title }}“</span>
          </button>
          <div :id="`opt-${c.id}`" class="ci-opts" :hidden="optsOpen !== String(c.id)">
            <button type="button" class="btn btn-quiet" @click="openRename(c)">
              <svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg>Umbenennen
            </button>
            <button type="button" class="btn btn-quiet danger" @click="openDelete(c)">
              <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>Löschen
            </button>
          </div>
        </li>
        <li v-if="listLoaded && !chats.length" class="empty">Noch keine Gespräche. Ihr erstes Anliegen erscheint dann hier.</li>
      </ul>
    </nav>

    <SettingsPage v-if="hash === SETTINGS" :user="user" @expired="emit('expired')" @saved="profileSaved" @deleted="emit('deleted')" />
    <section v-else class="pane" :class="activeId ? 'is-chat' : 'is-home'" aria-labelledby="view-h">
      <div v-if="activeId" ref="scroller" class="view">
        <button v-if="plan" type="button" class="plan-pin" @click="toPlan">
          <svg class="i" aria-hidden="true"><use href="#i-route" /></svg><span>Ihr Plan · {{ plan.status }}</span><span class="pin-go">Zum Plan</span>
        </button>
        <h1 id="view-h" class="chat-h" tabindex="-1">{{ active?.title ?? 'Gespräch' }}</h1>
        <ProfileCard class="chat-known" compact :profile="profile" :failed="profileFailed" />
        <p v-if="loading" class="muted">Nachrichten werden geladen …</p>
        <p v-else-if="loadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ loadErr }}</span></p>
        <p v-else-if="!messages.length" class="muted">Noch keine Nachrichten in diesem Gespräch.</p>
        <ol v-else class="msgs" aria-label="Nachrichten">
          <li v-for="m in messages" :id="`m-${m.key ?? m.id}`" :key="m.key ?? m.id" class="msg" :class="[m.role, m.kind]">
            <FactChips v-if="m === anchor && facts.length && (m.kind === 'plan' || m.kind === 'card')" class="msg-facts" :facts="facts" :disabled="!!run" @answer="editFact" />
            <p v-if="m.pending" class="typing" role="status">
              Der Lotse sucht die passenden Stellen<span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
            </p>
            <QuestionCard
              v-else-if="m.kind === 'question'"
              :text="m.text"
              :why="q(m).why"
              :chips="q(m).chips"
              :active="m === lastMsg && !run"
              :multi="!!q(m).multi"
              @answer="(chip) => answer(q(m).fact_key, chip)"
              @many="(chips) => answerMany(q(m).fact_key, chips)"
            />
            <NoticeCard v-else-if="m.kind === 'card'" :card="card(m)" :text="m.text" />
            <DocumentConfirm
              v-else-if="m.kind === 'confirm'"
              :text="m.text"
              :payload="m.payload as ConfirmPayload"
              :active="m === lastMsg && !run"
              @confirm="confirmLetter"
            />
            <div v-else-if="m.kind === 'plan'" class="plan-msg">
              <div class="bubble"><p>{{ m.text }}</p></div>
              <PlanView v-if="isCurrent(m)" :plan="plan!" :error="planErr" @update="patchStep" @upload="fileInput?.click()" />
              <p v-else class="muted">Dieser Plan wurde später angepasst. Der aktuelle Plan steht weiter unten.</p>
            </div>
            <div v-else class="bubble" :class="m.state">
              <div v-if="m.role === 'assistant'" class="md" v-html="m.html"></div>
              <p v-else-if="m.kind === 'document'" class="text"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg> {{ m.text }}</p>
              <p v-else class="text">{{ m.text }}</p>
              <p class="meta">
                <time :datetime="m.created_at">{{ when(m.created_at) }}</time>
                <span v-if="m.state" class="state" aria-live="polite">{{ STATE[m.state] }}</span>
              </p>
              <template v-if="m.state === 'failed'">
                <p class="err">{{ m.error }}</p>
                <button type="button" class="btn btn-secondary" @click="retry(activeId!, m)">Nochmal versuchen</button>
              </template>
            </div>
          </li>
        </ol>
      </div>
      <div v-else class="home navy-band">
        <h1 id="view-h" tabindex="-1">Guten Tag, {{ user.display_name }}.</h1>
        <p class="lead">Beschreiben Sie Ihr Anliegen in eigenen Worten.</p>
        <p v-if="notice" class="notice" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ notice }}</span></p>
      </div>

      <p class="sr" aria-live="polite">{{ announce }}</p>
      <form class="composer" :class="{ 'navy-band': !activeId }" novalidate @submit.prevent="submit">
        <label class="q-label" :class="{ sr: activeId }" for="q">{{ activeId ? 'Ihre Nachricht' : 'Worum geht es?' }}</label>
        <div class="cbox">
          <textarea
            id="q"
            v-model="draft"
            class="input"
            rows="2"
            maxlength="4000"
            :aria-invalid="!!draftErr"
            aria-describedby="q-err"
            @input="draftErr = ''"
            @keydown.enter.ctrl.prevent="submit"
            @keydown.enter.meta.prevent="submit"
          ></textarea>
          <div class="cbox-row">
            <input ref="fileInput" type="file" accept="application/pdf" class="sr" tabindex="-1" @change="upload" />
            <button type="button" class="btn btn-quiet" :aria-disabled="uploading || busy || !!run" @click="!uploading && !busy && !run && fileInput?.click()">
              <svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ uploading ? 'Brief wird gelesen …' : 'Entlassungsbrief (PDF)' }}
            </button>
            <button type="submit" class="btn btn-primary send" :aria-disabled="busy || !!run">
              {{ busy || run ? 'Einen Moment …' : 'Senden' }}<svg class="i" aria-hidden="true"><use href="#i-arrow" /></svg>
            </button>
          </div>
        </div>
        <p v-if="draftErr" id="q-err" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ draftErr }}</span></p>
      </form>
      <ProfileCard v-if="!activeId" :profile="profile" :failed="profileFailed" />
    </section>

    <dialog ref="renameDlg" class="small" aria-labelledby="rn-h">
      <form novalidate @submit.prevent="saveRename">
        <div class="dlg-head">
          <h2 id="rn-h">Gespräch umbenennen</h2>
          <button type="button" class="btn btn-quiet icon-only" aria-label="Schließen" @click="renameDlg?.close()">
            <svg class="i" aria-hidden="true"><use href="#i-x" /></svg>
          </button>
        </div>
        <div class="dlg-body">
          <div class="field">
            <label class="field-l" for="rn-input">Neuer Name</label>
            <input
              id="rn-input"
              ref="rnInput"
              v-model="newTitle"
              class="input"
              maxlength="100"
              autocomplete="off"
              autofocus
              :aria-invalid="!!dlgErr"
              aria-describedby="rn-err"
              @input="dlgErr = ''"
            />
            <p v-if="dlgErr" id="rn-err" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ dlgErr }}</span></p>
          </div>
        </div>
        <div class="dlg-foot">
          <button type="button" class="btn btn-secondary" @click="renameDlg?.close()">Abbrechen</button>
          <button type="submit" class="btn btn-primary">Speichern</button>
        </div>
      </form>
    </dialog>

    <dialog ref="deleteDlg" class="small" aria-labelledby="del-h" aria-describedby="del-d">
      <div class="dlg-head">
        <h2 id="del-h">Gespräch löschen?</h2>
        <button type="button" class="btn btn-quiet icon-only" aria-label="Schließen" @click="deleteDlg?.close()">
          <svg class="i" aria-hidden="true"><use href="#i-x" /></svg>
        </button>
      </div>
      <div class="dlg-body">
        <p id="del-d">„<b>{{ target?.title }}</b>“ und alle Nachrichten darin werden endgültig gelöscht. Das lässt sich nicht rückgängig machen.</p>
        <p v-if="dlgErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ dlgErr }}</span></p>
      </div>
      <div class="dlg-foot">
        <button type="button" class="btn btn-secondary" autofocus @click="deleteDlg?.close()">Abbrechen</button>
        <button type="button" class="btn btn-danger" @click="confirmDelete">
          <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>Endgültig löschen
        </button>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
/* Window never scrolls: only the chat list and the message list scroll inside themselves. */
.shell { height: 100%; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); }

/* Sidebar: a plain list of rows, the open one on the lavender band. */
.side { min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: .75rem; padding: 1.25rem 1rem; border-right: var(--hair); }
.side-h-row { display: flex; align-items: baseline; justify-content: space-between; gap: .5rem; margin-top: .75rem; padding-inline: .75rem; }
.side-h-row .muted { font-size: var(--fs-small); }
.side .btn-secondary { align-self: start; }
.chats { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: .25rem; }
.ci { position: relative; border-radius: var(--r-m); transition: background-color .15s; }
.ci:hover { background: var(--sunk); }
.ci.on { background: var(--accent-bg); }
.ci.on .ci-title { color: var(--head); }
/* The open chat: a green "you are here" dot, as in the mark. */
.ci.on .ci-title::before { content: ""; display: inline-block; width: .55rem; height: .55rem; margin-right: .5rem; border-radius: 50%; background: var(--accent); vertical-align: .1em; }
[data-contrast="high"] .ci.on { box-shadow: inset 0 0 0 2px var(--ink); }
.ci-link { display: grid; gap: .35rem; min-width: 0; padding: .7rem .75rem .75rem; border-radius: var(--r-m); color: var(--ink); text-decoration: none; }
.ci-link:focus-visible { outline-offset: -3px; }
.ci-title { padding-right: 2.4rem; font-weight: 600; line-height: 1.3; hyphens: auto; overflow-wrap: anywhere; }
.ci-when { font-size: var(--fs-small); color: var(--ink-3); }
.ci-more { position: absolute; top: .25rem; right: .25rem; width: 2.75rem; height: 2.75rem; display: grid; place-items: center; border: 0; border-radius: 50%; background: none; color: var(--ink-3); cursor: pointer; }
.ci-more:hover, .ci-more[aria-expanded="true"] { background: var(--sheet); color: var(--action); box-shadow: inset 0 0 0 1px var(--rule-2); }
.ci-opts { display: flex; flex-wrap: wrap; gap: .25rem; padding: 0 .4rem .5rem; }
.ci-opts[hidden] { display: none; }
.empty { padding: .25rem .75rem; color: var(--ink-3); }

.pane { --gut: max(1.25rem, calc((100% - 48rem) / 2)); min-width: 0; min-height: 0; display: flex; flex-direction: column; }

/* Home: greeting and the composer in one navy band, like a search field; what the Lotse knows below. */
.is-home { --gut: max(1.25rem, calc((100% - 44rem) / 2)); overflow-y: auto; }
.home { display: grid; gap: .5rem; padding: clamp(1.75rem, 6vh, 3rem) var(--gut) 1.5rem; }
.home h1 { font-size: clamp(var(--fs-h2), 5cqi, var(--fs-h1)); }
.lead { font-size: var(--fs-lead); color: var(--on-navy-2); }
.notice { display: flex; gap: .55em; align-items: flex-start; margin-top: .5rem; padding: .75rem 1rem; border-radius: var(--r-m); background: var(--sheet); color: var(--danger); font-weight: 600; }
.notice .i { margin-top: .15em; }
.is-home > :deep(.known) { margin: 2rem var(--gut); }

.view { flex: 1; min-height: 0; overflow-y: auto; padding: 2rem var(--gut) 1.5rem; }
.chat-h { font-size: var(--fs-h1); margin-bottom: 1.5rem; hyphens: auto; overflow-wrap: anywhere; }
.chat-known { margin-bottom: 1.75rem; }
.msgs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 1.25rem; }
.msg { display: flex; justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.bubble { max-width: min(34rem, 85%); display: grid; gap: .4rem; justify-items: start; padding: .7rem 1.1rem; border-radius: var(--r-l) var(--r-l) var(--r-s) var(--r-l); background: var(--accent-bg); }
.assistant .bubble { max-width: min(40rem, 92%); border-radius: var(--r-l) var(--r-l) var(--r-l) var(--r-s); background: var(--sheet); border: var(--hair); }
.bubble.failed { box-shadow: inset 0 0 0 2px var(--danger); }
.text { white-space: pre-wrap; overflow-wrap: anywhere; }

/* Assistant Markdown (v-html, so styled through :deep). */
.md { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.md > :deep(* + *) { margin-top: .65em; }
.md :deep(:is(ul, ol)) { margin-block: 0; padding-left: 1.4em; }
.md :deep(li + li), .md :deep(li > :is(ul, ol)) { margin-top: .25em; }
.md :deep(:is(h1, h2, h3, h4, h5, h6)) { margin-bottom: 0; font-size: var(--fs-lead); font-weight: 700; line-height: 1.3; color: var(--ink); }
.md :deep(a) { color: var(--head); }
.md :deep(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; padding: .1em .3em; border-radius: 5px; background: var(--sunk); }
.md :deep(pre) { margin-bottom: 0; overflow-x: auto; padding: .6rem .8rem; border-radius: var(--r-s); background: var(--sunk); }
.md :deep(pre code) { padding: 0; background: none; }
.md :deep(blockquote) { margin-inline: 0; padding-left: .8rem; border-left: 2px solid var(--rule-2); color: var(--ink-2); }
.md :deep(table) { display: block; overflow-x: auto; border-collapse: collapse; }
.md :deep(:is(th, td)) { padding: .3rem .6rem; border: 1px solid var(--rule-2); text-align: left; }
.md :deep(hr) { border: 0; border-top: var(--hair); }

/* While the reply is prepared: a line with typing dots. */
.typing { display: flex; align-items: center; gap: .6rem; color: var(--ink-2); }
.dots { display: inline-flex; gap: .3rem; }
.dots i { width: .45rem; height: .45rem; border-radius: 50%; background: var(--accent); opacity: .6; }
.dots i:nth-child(2) { animation-delay: .15s; }
.dots i:nth-child(3) { animation-delay: .3s; }
@media (prefers-reduced-motion: no-preference) { .dots i { animation: dot 1.2s ease-in-out infinite; } }
@keyframes dot { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }

/* Question, fact, card and plan replies use the full width, not a bubble. */
.msg.assistant:is(.question, .card, .plan, .confirm) { display: grid; gap: 1rem; justify-content: stretch; }
.msg-facts { margin-top: .25rem; }
.plan-msg { display: grid; gap: 1.5rem; }
.plan-msg > .bubble { justify-self: start; }
/* Sticks just below the top edge; the paper halo hides the text scrolling past it. */
.plan-pin { position: sticky; top: -1.5rem; z-index: 2; box-shadow: 0 0 0 .5rem var(--paper); display: flex; align-items: center; gap: .55rem; width: 100%; min-height: 2.75rem; margin: -1rem 0 1rem; padding: .45rem 1.1rem; border: 1px solid var(--turn-mark); border-radius: var(--r-pill); background: var(--turn-bg); color: var(--turn-ink); font: inherit; font-weight: 700; text-align: left; cursor: pointer; }
.plan-pin .pin-go { margin-left: auto; text-decoration: underline; text-underline-offset: .2em; }
.ci-status { margin-top: .1rem; }
.meta { display: flex; flex-wrap: wrap; gap: .1rem .75rem; font-size: var(--fs-small); color: var(--ink-3); }
.state { font-weight: 700; }
.delivered .state { color: var(--ready-ink); }
.failed .state { color: var(--danger); }

.composer { flex: none; display: grid; grid-template-columns: minmax(0, 1fr); gap: .65rem; padding: .75rem var(--gut) 1rem; border-top: var(--hair); }
.composer.navy-band { padding: 0 var(--gut) clamp(1.75rem, 6vh, 3rem); border: 0; }
.q-label { font-size: var(--fs-h3); font-weight: 600; }
.cbox { padding: .4rem; border: 1px solid var(--rule-2); border-radius: 1.6rem; background: var(--sheet); color: var(--ink); --focus: var(--action); }
.cbox:has(textarea:focus-visible) { outline: 3px solid var(--focus); outline-offset: 2px; }
.navy-band .cbox:has(textarea:focus-visible) { outline-color: var(--on-navy); }
.cbox:has([aria-invalid="true"]) { box-shadow: inset 0 0 0 2px var(--danger); }
.cbox textarea { border: 0; background: transparent; resize: none; min-height: 3rem; max-height: 14rem; field-sizing: content; padding: .55rem .9rem; }
.navy-band .cbox textarea { min-height: 5rem; }
.cbox textarea:focus-visible { outline: none; }
.cbox-row { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .75rem; padding-left: .3rem; }
.cbox-row .send { margin-left: auto; }
.navy-band .err { padding: .5rem .9rem; border-radius: var(--r-m); background: var(--sheet); }

@container (min-width: 56rem) {
  .shell { grid-template-columns: 20rem minmax(0, 1fr); }
}
/* Narrow: either the list or the chat, like the demo. */
@container (max-width: 55.99rem) {
  [data-pane="list"] .pane, [data-pane="main"] .side { display: none; }
  .side { padding: 1rem clamp(1rem, 4vw, 2rem) 2rem; border-right: 0; }
}
@media (forced-colors: active) {
  .ci.on { border: 2px solid CanvasText; }
}
</style>
