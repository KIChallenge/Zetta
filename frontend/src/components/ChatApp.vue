<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, shallowRef, watch } from 'vue'
import { ApiError, UNREACHABLE, type User } from '../auth'
import {
  createChat, deleteChat, listChats, listMessages, NOT_FOUND, renameChat, say, sendMessage, titleFrom, when,
  type Chat, type Message,
} from '../chats'
import { toHtml } from '../markdown'
import { getProfile, type Profile } from '../profile'
import ProfileCard from './ProfileCard.vue'
import SettingsPage from './SettingsPage.vue'

type Bubble = Message & {
  key?: number
  state?: 'sending' | 'delivered' | 'failed'
  error?: string
  html?: string // assistant only: sanitized Markdown
  streaming?: boolean
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
const run = shallowRef<{ chat: string; ctrl: AbortController } | null>(null) // the reply being requested or written
const writing = ref(false) // reply is streaming: Send becomes Stop
const announce = ref('')
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
// Measured before an update: streaming text only scrolls along if the user has not scrolled up to read.
const nearBottom = (el = scroller.value) => !!el && el.scrollHeight - el.scrollTop - el.clientHeight < 80
const put = (c: Chat) => (chats.value = [c, ...chats.value.filter((x) => x.id !== c.id)])
const drop = (b: Bubble) => {
  const i = messages.value.indexOf(b)
  if (i >= 0) messages.value.splice(i, 1)
}
const withHtml = (m: Message): Bubble => (m.role === 'assistant' ? { ...m, html: toHtml(m.text) } : m)

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
  loadErr.value = draftErr.value = ''
  loading.value = false
  if (id) notice.value = ''
  if (id && id === preset) return void (preset = null)
  messages.value = []
  if (!id) return
  loading.value = true
  try {
    const list = await listMessages(id)
    if (stale) return
    messages.value = list.map(withHtml)
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
    go(id, 'q')
  } catch (e) {
    draftErr.value = fail(e)
  }
  busy.value = false
  if (id) deliver(id, text)
}

function deliver(id: string, text: string) {
  const m: Bubble = reactive({ key: ++seq, id: '', role: 'user' as const, text, created_at: new Date().toISOString() })
  messages.value.push(m)
  scrollDown()
  retry(id, m)
}

const stop = () => writing.value && run.value?.ctrl.abort()

async function retry(id: string, m: Bubble) {
  if (run.value) return
  const ctrl = new AbortController()
  run.value = { chat: id, ctrl }
  m.state = 'sending'
  announce.value = ''
  const r: Bubble = reactive({
    key: ++seq, id: '', role: 'assistant' as const, text: '', created_at: new Date().toISOString(), html: '', streaming: true,
  })
  const births: number[] = [] // when each word first showed, for the fade-in
  let frame = 0
  let done = false
  const paint = () => {
    frame = 0
    const stick = nearBottom()
    r.html = toHtml(r.text, births, true)
    if (stick) scrollDown()
  }
  try {
    await sendMessage(id, m.text, ctrl.signal, (e) => {
      if (e.event === 'message') {
        Object.assign(m, e.data, { state: 'delivered' })
        writing.value = true
        // Right after its question, and only if that question is still shown.
        const i = messages.value.indexOf(m)
        if (i >= 0) {
          const stick = nearBottom()
          messages.value.splice(i + 1, 0, r)
          if (stick) scrollDown()
        }
        const c = chats.value.find((x) => String(x.id) === id)
        if (c) put({ ...c, updated_at: e.data.created_at })
      } else if (e.event === 'delta') {
        r.text += e.data.text
        frame ||= requestAnimationFrame(paint) // re-render Markdown at most once per frame
      } else if (e.event === 'title') {
        put(e.data)
      } else if (e.event === 'done') {
        Object.assign(r, e.data)
        done = true
      } else {
        throw new Error(e.data.detail)
      }
    })
    // A stream that ends without "done" lost its connection.
    if (!done) throw new ApiError(0, UNREACHABLE)
    announce.value = 'Antwort fertig'
  } catch (e) {
    // Stopped: keep the partial reply. Otherwise nothing was saved, so the question can be sent again.
    if (!ctrl.signal.aborted) {
      r.text = ''
      m.state = 'failed'
      m.error = e instanceof ApiError ? fail(e, 'Die Nachricht darf höchstens 4000 Zeichen lang sein.') : NO_REPLY
    }
  } finally {
    cancelAnimationFrame(frame)
    r.streaming = false
    r.html = toHtml(r.text, births) // no caret; words still fading in finish
    if (!r.text) drop(r)
    run.value = null
    writing.value = false
  }
  // The bubble grows by the retry button, which must not end up below the fold.
  if (m.state === 'failed' && messages.value.at(-1) === m) scrollDown()
}

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
        <h2 id="side-h" tabindex="-1">Ihre Gespräche</h2>
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
        <h1 id="view-h" class="chat-h" tabindex="-1">{{ active?.title ?? 'Gespräch' }}</h1>
        <ProfileCard class="chat-known" :profile="profile" :failed="profileFailed" />
        <p v-if="loading" class="muted">Nachrichten werden geladen …</p>
        <p v-else-if="loadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ loadErr }}</span></p>
        <p v-else-if="!messages.length" class="muted">Noch keine Nachrichten in diesem Gespräch.</p>
        <ol v-else class="msgs" aria-label="Nachrichten">
          <li v-for="m in messages" :key="m.key ?? m.id" class="msg" :class="m.role">
            <div class="bubble" :class="m.state">
              <p v-if="m.streaming && !m.html" class="dots"><i></i><i></i><i></i><span class="sr">Antwort wird geschrieben …</span></p>
              <div v-else-if="m.role === 'assistant'" class="md" v-html="m.html"></div>
              <p v-else class="text">{{ m.text }}</p>
              <p v-if="!m.streaming" class="meta">
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
      <div v-else class="home">
        <h1 id="view-h" tabindex="-1">Guten Tag, {{ user.display_name }}.</h1>
        <p class="lead">Beschreiben Sie Ihr Anliegen in eigenen Worten.</p>
        <p v-if="notice" class="notice" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ notice }}</span></p>
      </div>

      <p class="sr" aria-live="polite">{{ announce }}</p>
      <form class="composer" novalidate @submit.prevent="submit" @keydown.esc="stop">
        <label class="q-label" :class="{ sr: activeId }" for="q">{{ activeId ? 'Ihre Nachricht' : 'Worum geht es?' }}</label>
        <div class="cbox">
          <textarea
            id="q"
            v-model="draft"
            class="input"
            rows="2"
            maxlength="4000"
            :aria-invalid="!!draftErr"
            aria-describedby="q-hint q-err"
            @input="draftErr = ''"
            @keydown.enter.ctrl.prevent="submit"
            @keydown.enter.meta.prevent="submit"
          ></textarea>
          <div class="cbox-row">
            <span id="q-hint" class="hint">{{ writing ? 'Stoppen mit Esc' : 'Senden mit Strg + Enter (Mac: ⌘ + Enter)' }}</span>
            <!-- One button that changes role, so focus stays on it when it turns into Stop. -->
            <button
              :type="writing ? 'button' : 'submit'"
              class="btn btn-primary send"
              :aria-disabled="busy || (!!run && !writing)"
              @click="stop"
            >
              <template v-if="writing">Stoppen<svg class="i" aria-hidden="true"><use href="#i-stop" /></svg></template>
              <template v-else>
                {{ busy || run ? 'Einen Moment …' : 'Senden' }}<svg class="i" aria-hidden="true"><use href="#i-arrow" /></svg>
              </template>
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

.side { min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: .75rem; padding: 1rem; box-shadow: inset -1px 0 0 var(--rule); }
.side-h-row { display: flex; align-items: baseline; justify-content: space-between; gap: .5rem; margin-top: .6rem; padding-inline: .3rem; }
.side-h-row h2 { font-size: 1.05rem; }
.side .btn-secondary { align-self: start; }
.chats { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: .6rem; }
.ci { position: relative; border-radius: var(--r-m); background: var(--sheet); box-shadow: 0 0 0 1px var(--rule), 0 1px 2px rgba(17, 33, 42, .05); transition: box-shadow .15s; }
.ci:hover { box-shadow: 0 0 0 1px var(--rule-2), 0 3px 8px -3px rgba(17, 33, 42, .15); }
.ci.on { box-shadow: 0 0 0 2px var(--harbor); }
.ci.on .ci-title { color: var(--harbor); }
.ci-link { display: grid; gap: .35rem; min-width: 0; padding: .65rem .8rem .7rem; border-radius: var(--r-m); color: var(--ink); text-decoration: none; }
.ci-title { padding-right: 2.4rem; font-weight: 700; line-height: 1.3; hyphens: auto; overflow-wrap: anywhere; }
.ci-when { font-size: .85rem; color: var(--ink-3); }
.ci-more { position: absolute; top: .2rem; right: .2rem; width: 2.75rem; height: 2.75rem; display: grid; place-items: center; border: 0; border-radius: var(--r-s); background: none; color: var(--ink-3); cursor: pointer; }
.ci-more:hover, .ci-more[aria-expanded="true"] { background: var(--harbor-tint); color: var(--harbor); }
.ci-opts { display: flex; flex-wrap: wrap; gap: .25rem; padding: 0 .4rem .5rem; }
.ci-opts[hidden] { display: none; }
.empty { padding: .25rem .3rem; color: var(--ink-3); }

.pane { --gut: max(1.25rem, calc((100% - 48rem) / 2)); min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.is-home { --gut: max(1.25rem, calc((100% - 42rem) / 2)); overflow-y: auto; gap: 1.5rem; padding: clamp(1.25rem, 5vh, 3rem) var(--gut); }
.home { display: grid; gap: .6rem; }
.home h1 { font-size: clamp(1.75rem, 4vw, 2.1rem); }
.lead { font-size: 1.2rem; color: var(--ink-2); }
.notice { display: flex; gap: .55em; align-items: flex-start; margin-top: .5rem; padding: .75rem 1rem; border-radius: var(--r-m); background: color-mix(in srgb, var(--danger) 10%, var(--sheet)); color: var(--danger); font-weight: 600; }
.notice .i { margin-top: .15em; }

.view { flex: 1; min-height: 0; overflow-y: auto; padding: 2rem var(--gut) 1.5rem; }
.chat-h { font-size: 1.9rem; margin-bottom: 1.75rem; hyphens: auto; overflow-wrap: anywhere; }
.chat-known { margin-bottom: 1.75rem; }
.msgs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 1.1rem; }
.msg { display: flex; justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.bubble { max-width: min(34rem, 85%); display: grid; gap: .4rem; justify-items: start; padding: .7rem 1rem; border-radius: var(--r-l) var(--r-l) .35rem var(--r-l); background: var(--harbor-tint); }
.assistant .bubble { border-radius: var(--r-l) var(--r-l) var(--r-l) .35rem; background: var(--sheet); box-shadow: 0 0 0 1px var(--rule); }
.bubble.failed { box-shadow: inset 0 0 0 2px var(--danger); }
.text { white-space: pre-wrap; overflow-wrap: anywhere; }
.assistant .bubble { max-width: min(40rem, 92%); }

/* Assistant Markdown (v-html, so styled through :deep). */
.md { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.md > :deep(* + *) { margin-top: .65em; }
.md :deep(:is(ul, ol)) { margin-block: 0; padding-left: 1.4em; }
.md :deep(li + li), .md :deep(li > :is(ul, ol)) { margin-top: .25em; }
.md :deep(:is(h1, h2, h3, h4, h5, h6)) { margin-bottom: 0; font-size: 1.05rem; line-height: 1.3; }
.md :deep(a) { color: var(--harbor); }
.md :deep(code) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em; padding: .1em .3em; border-radius: 5px; background: var(--sunk); }
.md :deep(pre) { margin-bottom: 0; overflow-x: auto; padding: .6rem .8rem; border-radius: var(--r-s); background: var(--sunk); }
.md :deep(pre code) { padding: 0; background: none; }
.md :deep(blockquote) { margin-inline: 0; padding-left: .8rem; border-left: 3px solid var(--rule-2); color: var(--ink-2); }
.md :deep(table) { display: block; overflow-x: auto; border-collapse: collapse; }
.md :deep(:is(th, td)) { padding: .3rem .6rem; border: 1px solid var(--rule-2); text-align: left; }
.md :deep(hr) { border: 0; border-top: 1px solid var(--rule-2); }

/* Streaming: typing dots, then words fade in (duration = FADE_MS in markdown.ts) behind a blinking caret. */
.dots { display: flex; gap: .3rem; padding-block: .55rem; }
.dots i { width: .5rem; height: .5rem; border-radius: 50%; background: var(--ink-3); animation: dot 1.2s ease-in-out infinite; }
.dots i:nth-child(2) { animation-delay: .15s; }
.dots i:nth-child(3) { animation-delay: .3s; }
.md :deep(.w) { animation: word-in 400ms ease-out both; }
.md :deep(.caret) { display: inline-block; width: 2px; height: 1.1em; margin-left: 2px; vertical-align: text-bottom; background: var(--harbor); animation: blink 1s steps(1) infinite; }
@keyframes dot { 0%, 70%, 100% { opacity: .35; transform: none; } 35% { opacity: 1; transform: translateY(-3px); } }
@keyframes word-in { from { opacity: 0; } }
@keyframes blink { 50% { opacity: 0; } }
.meta { display: flex; flex-wrap: wrap; gap: .1rem .75rem; font-size: .85rem; color: var(--ink-3); }
.state { font-weight: 700; }
.delivered .state { color: var(--ready-ink); }
.failed .state { color: var(--danger); }

.composer { flex: none; display: grid; grid-template-columns: minmax(0, 1fr); gap: .65rem; padding: .75rem var(--gut) 1rem; box-shadow: 0 -1px 0 var(--rule); }
.is-home .composer { padding: 1.25rem 1.35rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.q-label { font-size: 1.35rem; font-weight: 700; }
.cbox { background: var(--sheet); border-radius: var(--r-l); box-shadow: var(--lift); padding: .45rem; }
.cbox:focus-within { box-shadow: var(--lift), 0 0 0 3px var(--focus); }
.is-home .cbox { background: var(--sunk); box-shadow: inset 0 0 0 1px var(--rule-2); }
.is-home .cbox:focus-within { box-shadow: inset 0 0 0 1px var(--rule-2), 0 0 0 3px var(--focus); }
.cbox:has([aria-invalid="true"]) { box-shadow: inset 0 0 0 2px var(--danger); }
.cbox textarea { border: 0; background: transparent; resize: none; min-height: 3rem; max-height: 14rem; field-sizing: content; padding: .55rem .7rem; }
.is-home .cbox textarea { min-height: 5rem; }
.cbox textarea:focus-visible { outline: none; }
.cbox-row { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .75rem; padding-left: .7rem; }
.cbox-row .hint { font-size: .85rem; }
.cbox-row .send { margin-left: auto; }
@media (pointer: coarse) { .cbox-row .hint { display: none; } }

@container (min-width: 56rem) {
  .shell { grid-template-columns: 20rem minmax(0, 1fr); }
}
/* Narrow: either the list or the chat, like the demo. */
@container (max-width: 55.99rem) {
  [data-pane="list"] .pane, [data-pane="main"] .side { display: none; }
  .side { padding: 1rem clamp(1rem, 4vw, 2rem) 2rem; }
}
@media (forced-colors: active) {
  .ci, .bubble { border: 1px solid CanvasText; }
}
</style>
