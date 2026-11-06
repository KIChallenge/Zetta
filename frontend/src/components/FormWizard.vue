<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ApiError } from '../auth'
import {
  downloadForm, formHelp, getWizard, saveAnswers, say,
  type Finding, type Hint, type HelpBody, type Wizard, type WizardQuestion, type WizardSection,
} from '../chats'
import { fmtDate, fmtPhone, fmtSvnr } from '../fields'
import { k, locale, t, translating } from '../i18n'
import { follows, problem, shownIds, viennaCity, wire, type Problem } from '../wizard'

// The whole form, one section per screen. The backend provides every value and checks every answer; the LLM help
// (explain, draft, question box, final check) is optional and the wizard works the same without it.
const props = defineProps<{ chat: string | number; step: string; title: string }>()
const emit = defineEmits<{ close: [changed: { saved: boolean; remembered: boolean }] }>()

const PROBLEMS: Record<Exclude<Problem, ''>, string> = {
  date: k('Bitte als TT.MM.JJJJ eingeben, zum Beispiel 01.03.2026.'),
  birth: k('Bitte prüfen Sie das Geburtsdatum.'),
  svnr: k('Diese Nummer gibt es nicht. Bitte vergleichen Sie die Ziffern mit Ihrer e-card.'),
  postal: k('Die Postleitzahl hat 4 Ziffern, zum Beispiel 1100.'),
  email: k('Bitte prüfen Sie die E-Mail-Adresse. Sie sieht so aus: name@beispiel.at'),
  phone: k('Bitte nur Ziffern, Leerzeichen und +.'),
  number: k('Bitte nur Ziffern.'),
  long: k('Das ist länger, als im Formular Platz hat. Bitte kürzen Sie es.'),
}
const SOURCES: Record<string, string> = { profile: k('Aus Ihrem Profil'), kept: k('Gemerkt aus einem früheren Antrag'), constant: k('Vorgabe') }

const dlg = ref<HTMLDialogElement>()
const body = ref<HTMLElement>()
const data = ref<Wizard | null>(null)
const loadErr = ref('')
const at = ref(0) // the section shown; sections.length is the review
const values = reactive<Record<string, string>>({}) // as shown in the inputs
const saved = reactive<Record<string, string>>({}) // as last saved, the same way
const errors = reactive<Record<string, string>>({})
const saving = ref(false)
const saveErr = ref('')
const savedOnce = ref(false)
const remembered = ref(false)
const confirmClose = ref(false)
const remember = ref(true)
const downloadErr = ref('')
type Help = { state: 'loading' | 'done' | 'fail'; text?: string }
const explained = reactive<Record<string, Help>>({})
const drafts = reactive<Record<string, { state: 'loading' | 'done' | 'fail'; before: string }>>({})
const askText = ref('')
const asked = ref<Help & { refused?: boolean }>()
const hints = ref<{ state: 'loading' | 'done' | 'fail'; items: Hint[] }>()

const sections = computed(() => data.value?.sections ?? [])
const review = computed(() => at.value === sections.value.length)
const current = computed<WizardSection | undefined>(() => sections.value[at.value])
const stations = computed(() => [...sections.value.map((s) => s.title), k('Prüfen')])
const ids = computed(() => new Set(sections.value.flatMap((s) => s.questions.map((q) => q.id))))
const shown = computed(() => shownIds(sections.value, data.value?.facts ?? {}, values))
const visible = (s: WizardSection) => s.questions.filter((q) => shown.value.has(q.id))
const dirty = (q: WizardQuestion) => wire(q, values[q.id] ?? '') !== wire(q, saved[q.id] ?? '') && drafts[q.id]?.state !== 'done'
const unsaved = computed(() => sections.value.some((s) => s.questions.some(dirty)))
const findings = computed(() => data.value?.findings ?? [])
const sectionTitle = (id?: string) => t(sections.value.find((s) => s.id === id)?.title ?? '')

// The paper parts, grouped by where they are on the form.
const paper = computed(() => {
  const groups = new Map<string, string[]>()
  for (const m of data.value?.manual ?? []) {
    const where = m.point ? t('Seite {page}, Punkt {point}', { page: m.page ?? '', point: m.point }) : t('Seite {page}', { page: m.page ?? '' })
    groups.set(where, [...(groups.get(where) ?? []), m.label])
  }
  return [...groups].map(([where, labels]) => ({ where, labels }))
})

const show = (q: WizardQuestion, v: string) => (q.detail === 'svnr' ? fmtSvnr(v) : v)
/** The server's state. What was just saved (`sent`) shows as stored; other changes being typed stay. */
function take(w: Wizard, sent: string[] = []) {
  data.value = w
  for (const q of w.sections.flatMap((s) => s.questions)) {
    if (!(q.id in values) || sent.includes(q.id) || !dirty(q)) values[q.id] = show(q, q.value)
    saved[q.id] = show(q, q.value)
  }
}

onMounted(async () => {
  dlg.value?.showModal()
  try {
    take(await getWizard(props.chat, props.step))
    focusHeading()
  } catch (e) {
    loadErr.value = say(e)
  }
})

async function focusHeading() {
  await nextTick()
  if (body.value) body.value.scrollTop = 0
  if (dlg.value) dlg.value.scrollTop = 0
  document.getElementById('wz-h')?.focus({ preventScroll: true })
}

function label(q: WizardQuestion) {
  return q.kind === 'checkbox' ? '' : q.label
}
// In another language the German label stays, as on the paper form, and its translation sits below it.
const translation = (text: string | null) => (text && translating.value && t(text) !== text ? t(text) : '')
function answerText(q: WizardQuestion) {
  const v = values[q.id] ?? ''
  if (!v) return ''
  if (q.kind === 'checkbox') return t('Ja')
  return q.options[v] !== undefined ? t(q.options[v]!) : v
}
function sourceNote(q: WizardQuestion) {
  if (!q.source || q.source === 'answer' || dirty(q) || !values[q.id]) return ''
  if (q.source === 'fact') return `${t('Aus dem Gespräch')}: ${t(q.source_label ?? '')}`
  return t(SOURCES[q.source] ?? '')
}

function onInput(q: WizardQuestion, section: WizardSection) {
  const v = values[q.id] ?? ''
  if (q.kind === 'date') values[q.id] = fmtDate(v)
  else if (q.detail === 'svnr') values[q.id] = fmtSvnr(v.replace(/\D/g, '').slice(0, 10))
  else if (q.detail === 'phone') values[q.id] = fmtPhone(v)
  else if (q.detail === 'postal_code') {
    values[q.id] = v.replace(/\D/g, '').slice(0, 4)
    const city = section.questions.find((c) => c.detail === 'city')
    if (city) values[city.id] = viennaCity(values[q.id]!, values[city.id] ?? '')
  }
  if (errors[q.id]) errors[q.id] = message(q)
}
function message(q: WizardQuestion) {
  const p = problem(q, values[q.id] ?? '')
  return p ? t(PROBLEMS[p]) : ''
}
function pick(q: WizardQuestion, value: string) {
  values[q.id] = values[q.id] === value ? '' : value
}

/** Checks the section's shown answers; focuses the first wrong one. */
function valid(s: WizardSection) {
  let first = ''
  for (const q of visible(s)) {
    errors[q.id] = message(q)
    if (errors[q.id]) first ||= q.id
  }
  if (first) document.getElementById(`wq-${first}`)?.focus()
  return !first
}

/** Saves the section's changed answers. False if that failed: the user stays on the section. */
async function save(s: WizardSection) {
  const changed = s.questions.filter(dirty)
  if (!changed.length) return true
  saving.value = true
  saveErr.value = ''
  try {
    const answers = Object.fromEntries(changed.map((q) => [q.id, wire(q, values[q.id] ?? '')]))
    take(await saveAnswers(props.chat, props.step, answers), Object.keys(answers))
    savedOnce.value = true
    return true
  } catch (e) {
    const id = e instanceof ApiError && e.status === 422 ? /^invalid:(.+)$/.exec(e.message)?.[1] : undefined
    if (id) {
      errors[id] = t('Bitte prüfen Sie diese Angabe.')
      document.getElementById(`wq-${id}`)?.focus()
    } else saveErr.value = say(e)
    return false
  } finally {
    saving.value = false
  }
}

async function go(to: number, focus?: string) {
  const s = current.value
  if (s && to !== at.value && (!valid(s) || !(await save(s)))) return
  at.value = to
  if (review.value) check()
  await focusHeading()
  if (focus) document.getElementById(`wq-${focus}`)?.focus()
}

function close() {
  if (unsaved.value && !confirmClose.value) {
    confirmClose.value = true
    return
  }
  dlg.value?.close()
  emit('close', { saved: savedOnce.value, remembered: remembered.value })
}
async function saveAndClose() {
  confirmClose.value = false
  if (current.value && (!valid(current.value) || !(await save(current.value)))) return
  close()
}
function discard() {
  for (const q of sections.value.flatMap((s) => s.questions)) values[q.id] = saved[q.id] ?? ''
  confirmClose.value = false
  close()
}

// ---- The optional LLM layer ----

async function help(body: HelpBody) {
  return formHelp(props.chat, props.step, body)
}
async function explain(q: WizardQuestion) {
  if (explained[q.id]?.state === 'done' || explained[q.id]?.state === 'loading') {
    delete explained[q.id] // a second click closes it
    return
  }
  explained[q.id] = { state: 'loading' }
  try {
    explained[q.id] = { state: 'done', text: (await help({ kind: 'explain', question: q.id })).text }
  } catch {
    explained[q.id] = { state: 'fail' }
  }
}
async function suggest(q: WizardQuestion) {
  const before = values[q.id] ?? ''
  drafts[q.id] = { state: 'loading', before }
  try {
    values[q.id] = (await help({ kind: 'suggest', question: q.id })).text ?? before
    drafts[q.id] = { state: 'done', before }
  } catch {
    drafts[q.id] = { state: 'fail', before }
  }
}
function accept(q: WizardQuestion) {
  delete drafts[q.id]
}
function reject(q: WizardQuestion) {
  values[q.id] = drafts[q.id]?.before ?? ''
  delete drafts[q.id]
}
async function ask() {
  if (!askText.value.trim()) return
  asked.value = { state: 'loading' }
  try {
    const reply = await help({ kind: 'ask', text: askText.value })
    asked.value = { state: 'done', text: reply.text, refused: reply.refused }
  } catch {
    asked.value = { state: 'fail' }
  }
}
let checked = '' // the answers the hints are about: unchanged, the review asks no second time
async function check() {
  const now = JSON.stringify(saved)
  if (now === checked && hints.value?.state === 'done') return
  checked = now
  hints.value = { state: 'loading', items: [] }
  try {
    hints.value = { state: 'done', items: (await help({ kind: 'check' })).hints ?? [] }
  } catch {
    hints.value = { state: 'fail', items: [] }
  }
}

function where(f: Finding | Hint) {
  const index = sections.value.findIndex((s) => s.id === f.section)
  if (index >= 0) go(index, f.question)
}

async function download() {
  downloadErr.value = ''
  try {
    await downloadForm(props.chat, props.step, { user: {}, subject: {}, remember: remember.value })
    remembered.value ||= remember.value
  } catch (e) {
    downloadErr.value = say(e)
  }
}
</script>

<template>
  <dialog ref="dlg" class="wz" aria-labelledby="wz-t" @cancel.prevent="close">
    <header class="wz-head">
      <h2 id="wz-t" class="wz-title">{{ title }}</h2>
      <button type="button" class="btn btn-quiet icon-only" :aria-label="t('Schließen')" @click="close"><svg class="i" aria-hidden="true"><use href="#i-x" /></svg></button>
    </header>

    <nav v-if="data" class="prog" :aria-label="t('Abschnitte')">
      <p class="wz-sub">
        <span v-if="data.subject">{{ t('Für wen') }}: {{ t(data.subject) }}</span>
        <span class="saved" aria-live="polite"><template v-if="saving">{{ t('Wird gespeichert …') }}</template><template v-else-if="savedOnce"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Gespeichert') }}</template></span>
      </p>
      <ol class="rail">
        <li v-for="(name, i) in stations" :key="i" :class="i < at ? 'done' : i === at ? 'now' : 'later'" :aria-current="i === at ? 'step' : undefined">
          <button type="button" @click="go(i)">
            <span class="dot" aria-hidden="true"><svg v-if="i < at" class="i"><use href="#i-check" /></svg></span>
            <span class="label">{{ t(name) }}</span>
          </button>
        </li>
      </ol>
      <p class="rail-now">{{ t('Schritt {n} von {total}: {name}', { n: at + 1, total: stations.length, name: t(stations[at] ?? '') }) }}</p>
    </nav>

    <div ref="body" class="wz-body">
      <p v-if="loadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ t(loadErr) }}</span></p>
      <p v-else-if="!data" class="hint" role="status">{{ t('Wird geladen …') }}</p>

      <!-- One section -->
      <section v-else-if="current" class="wz-in" aria-labelledby="wz-h">
        <div class="sec-h">
          <p v-if="current.page" class="caps">{{ current.point ? t('Formular Seite {page}, Punkt {point}', { page: current.page, point: current.point }) : t('Formular Seite {page}', { page: current.page }) }}</p>
          <h3 id="wz-h" tabindex="-1">{{ current.heading ?? current.title }}</h3>
          <p v-if="translation(current.heading)" class="tr" :lang="locale">{{ translation(current.heading) }}</p>
        </div>

        <div v-for="q in visible(current)" :key="q.id" class="q" :class="{ follow: follows(q, ids) }">
          <template v-if="q.kind === 'checkbox'">
            <label class="check">
              <input :id="`wq-${q.id}`" type="checkbox" :checked="values[q.id] === 'yes'" :aria-describedby="`wq-${q.id}-h`" @change="values[q.id] = ($event.target as HTMLInputElement).checked ? 'yes' : ''" />
              <span><b>{{ q.label }}</b><small v-if="translation(q.label)" :lang="locale">{{ translation(q.label) }}</small></span>
            </label>
          </template>
          <template v-else>
            <component :is="q.kind === 'choice' || q.kind === 'yes_no' ? 'p' : 'label'" :id="`wq-${q.id}-l`" class="q-l" :for="q.kind === 'choice' || q.kind === 'yes_no' ? undefined : `wq-${q.id}`">
              {{ label(q) }}<span v-if="q.required" class="sr"> ({{ t('Pflichtangabe') }})</span>
              <span v-if="translation(q.label)" class="tr" :lang="locale">{{ translation(q.label) }}</span>
            </component>
          </template>
          <p :id="`wq-${q.id}-h`" class="hint q-help" :hidden="!q.help && !sourceNote(q)">
            <span v-if="q.help">{{ q.help }}<template v-if="translation(q.help)"><br /><span :lang="locale">{{ translation(q.help) }}</span></template></span>
            <a v-if="q.help && q.source_url" class="src-link" :href="q.source_url" target="_blank" rel="noopener noreferrer"> {{ t('Quelle') }}</a>
            <span v-if="sourceNote(q)" class="src"><svg class="i" aria-hidden="true"><use :href="q.source === 'fact' ? '#i-chat' : '#i-user'" /></svg>{{ sourceNote(q) }}</span>
          </p>

          <div v-if="q.kind === 'choice' || q.kind === 'yes_no'" class="chips" role="group" :aria-labelledby="`wq-${q.id}-l`" :aria-describedby="`wq-${q.id}-h`">
            <button v-for="(text, value, n) in q.options" :id="n === 0 ? `wq-${q.id}` : undefined" :key="value" type="button" class="chip" :aria-pressed="values[q.id] === value" @click="pick(q, String(value))">{{ t(text) }}</button>
          </div>
          <div v-else-if="q.kind === 'multiline'" class="draft" :class="{ suggested: drafts[q.id]?.state === 'done' }">
            <span v-if="drafts[q.id]?.state === 'done'" class="pill" data-tone="wait">{{ t('Vorschlag der KI, noch nicht übernommen') }}</span>
            <textarea :id="`wq-${q.id}`" v-model="values[q.id]" class="input" rows="3" :maxlength="q.max ?? undefined" :aria-invalid="!!errors[q.id]" :aria-describedby="`wq-${q.id}-h wq-${q.id}-e${drafts[q.id] ? ` wq-${q.id}-d` : ''}`" @input="onInput(q, current)"></textarea>
            <template v-if="drafts[q.id]?.state === 'done'">
              <p :id="`wq-${q.id}-d`" class="hint">{{ t('Aus Ihren Antworten und den Hinweisen im Formular. Bitte prüfen und ändern, was nicht stimmt.') }}</p>
              <div class="actions">
                <button type="button" class="btn btn-secondary" @click="accept(q)"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Übernehmen') }}</button>
                <button type="button" class="btn btn-quiet" @click="reject(q)">{{ t('Verwerfen') }}</button>
              </div>
            </template>
            <p v-else-if="drafts[q.id]?.state === 'fail'" :id="`wq-${q.id}-d`" class="hint" role="status">{{ t('Ein Vorschlag ist gerade nicht möglich. Sie können den Text selbst schreiben.') }}</p>
          </div>
          <input
            v-else-if="q.kind !== 'checkbox'"
            :id="`wq-${q.id}`"
            v-model="values[q.id]"
            class="input"
            :class="{ short: q.kind === 'date' || q.detail === 'postal_code' || q.detail === 'svnr' }"
            :type="q.detail === 'email' ? 'email' : q.detail === 'phone' ? 'tel' : 'text'"
            :inputmode="q.kind === 'date' || q.kind === 'number' || q.detail === 'svnr' || q.detail === 'postal_code' ? 'numeric' : undefined"
            :placeholder="q.kind === 'date' ? t('TT.MM.JJJJ') : undefined"
            :maxlength="q.kind === 'date' ? 10 : q.detail === 'svnr' ? 11 : (q.max ?? undefined)"
            autocomplete="off"
            :aria-invalid="!!errors[q.id]"
            :aria-describedby="`wq-${q.id}-h wq-${q.id}-e`"
            @input="onInput(q, current)"
            @blur="values[q.id]?.trim() && (errors[q.id] = message(q))"
          />
          <p :id="`wq-${q.id}-e`" class="err" :hidden="!errors[q.id]"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors[q.id] }}</span></p>

          <div v-if="!q.detail || q.suggest" class="q-tools">
            <!-- A person's own details (name, address) need no explanation; the form's questions may. -->
            <button v-if="!q.detail" type="button" class="linkbtn" :aria-expanded="!!explained[q.id]" :aria-controls="`wq-${q.id}-x`" @click="explain(q)"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span>{{ t('Was heißt das?') }}</span></button>
            <button v-if="q.suggest && drafts[q.id]?.state !== 'done'" type="button" class="linkbtn" :aria-disabled="drafts[q.id]?.state === 'loading'" @click="drafts[q.id]?.state !== 'loading' && suggest(q)"><svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg><span>{{ drafts[q.id]?.state === 'loading' ? t('Vorschlag wird geschrieben …') : t('Vorschlag machen') }}</span></button>
          </div>
          <div v-if="explained[q.id]" :id="`wq-${q.id}-x`" class="explain" role="status">
            <p v-if="explained[q.id]!.state === 'loading'" class="hint">{{ t('Einen Moment …') }}</p>
            <p v-else-if="explained[q.id]!.state === 'fail'">{{ t('Die Erklärung ist gerade nicht verfügbar. Der Hinweis oben stammt aus dem Formular.') }}</p>
            <template v-else>
              <p>{{ explained[q.id]!.text }}</p>
              <p class="who"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg>{{ t('Erklärt von der KI. Es gilt, was im Formular steht.') }}</p>
            </template>
          </div>
        </div>
      </section>

      <!-- Review -->
      <section v-else class="wz-in" aria-labelledby="wz-h">
        <div class="sec-h">
          <h3 id="wz-h" tabindex="-1">{{ t('Prüfen und herunterladen') }}</h3>
          <p>{{ t('Sehen Sie die Angaben noch einmal durch. Was unter „Selbst ausfüllen“ steht, tragen Sie von Hand ins Formular ein.') }}</p>
        </div>

        <section class="find" aria-labelledby="wz-f">
          <h4 id="wz-f">{{ t('Bitte noch ansehen') }}</h4>
          <p v-if="!findings.length" class="ok"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Alle Pflichtangaben sind da.') }}</p>
          <ul v-else>
            <li v-for="(f, n) in findings" :key="n" :class="`f-${f.kind}`">
              <svg class="i" aria-hidden="true"><use :href="f.kind === 'missing' ? '#i-alert' : '#i-info'" /></svg>
              <span v-if="f.kind === 'missing'"><b>{{ f.label }}</b> {{ t('fehlt noch') }} <span class="hint">· {{ sectionTitle(f.section) }}</span></span>
              <span v-else>{{ t(f.text ?? '') }}</span>
              <button v-if="f.kind === 'missing'" type="button" class="btn btn-quiet" @click="where(f)">{{ t('Ergänzen') }}</button>
            </li>
          </ul>
          <p class="ai-h"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg>{{ t('Zusätzlich von der KI geprüft') }}</p>
          <p v-if="hints?.state === 'loading'" class="hint" role="status">{{ t('Die KI sieht die Antworten noch durch …') }}</p>
          <p v-else-if="hints?.state === 'fail'" class="hint" role="status">{{ t('Die zusätzliche Prüfung ist gerade nicht verfügbar.') }}</p>
          <p v-else-if="hints && !hints.items.length" class="hint" role="status">{{ t('Keine weiteren Hinweise.') }}</p>
          <ul v-else-if="hints" class="ai" role="status">
            <li v-for="h in hints.items" :key="h.question + h.text">
              <svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span>{{ h.text }}</span>
              <button type="button" class="btn btn-quiet" @click="where(h)">{{ t('Ansehen') }}</button>
            </li>
          </ul>
        </section>

        <section class="block" aria-labelledby="wz-a">
          <h4 id="wz-a">{{ t('Ihre Angaben') }}</h4>
          <div v-for="(s, i) in sections" :key="s.id" class="sum">
            <div class="sum-h"><h5>{{ t(s.title) }}</h5><button type="button" class="btn btn-quiet" @click="go(i)">{{ t('Ändern') }}</button></div>
            <dl>
              <template v-for="q in visible(s)" :key="q.id">
                <template v-if="values[q.id] || q.required">
                  <dt>{{ q.label }}</dt>
                  <dd :class="{ empty: !values[q.id] }">{{ values[q.id] ? answerText(q) : t('noch offen') }}</dd>
                </template>
              </template>
            </dl>
          </div>
        </section>

        <section class="block" aria-labelledby="wz-p">
          <h4 id="wz-p">{{ t('Selbst ausfüllen') }}</h4>
          <p class="hint">{{ t('Diese Teile füllt der Lotse nie aus: Angaben zur Gesundheit, Zustimmungen, das Datum und Ihre Unterschrift.') }}</p>
          <ul class="paper">
            <li v-for="g in paper" :key="g.where"><span class="where">{{ g.where }}</span><span>{{ g.labels.join(' · ') }}</span></li>
          </ul>
        </section>

        <label class="check">
          <input v-model="remember" type="checkbox" />
          <span><b>{{ t('Für weitere Anträge merken') }}</b><small>{{ t('Dann sind Name, Adresse und Versicherungsnummer im nächsten Formular schon eingetragen. Sie können sie in den Einstellungen ändern oder löschen.') }}</small></span>
        </label>

        <div class="send">
          <div class="actions"><button type="button" class="btn btn-primary" @click="download"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ t('Antrag herunterladen (PDF)') }}</button></div>
          <p v-if="downloadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ t(downloadErr) }}</span></p>
          <p v-if="data.submit_to" class="to"><svg class="i" aria-hidden="true"><use href="#i-building" /></svg><span>{{ t('Unterschrieben schicken oder bringen an:') }}<br /><b>{{ data.submit_to.name }}</b><template v-if="data.submit_to.address"><br />{{ data.submit_to.address }}</template></span></p>
          <div class="actions">
            <a v-if="data.form.online_url" class="btn btn-secondary" :href="data.form.online_url" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-ext" /></svg>{{ t('Lieber online stellen') }}</a>
            <a class="btn btn-quiet" :href="data.form.url" target="_blank" rel="noopener noreferrer">{{ t('Leeres Formular') }}</a>
          </div>
        </div>
      </section>

      <!-- The question box, on every screen -->
      <details v-if="data" class="ask">
        <summary class="more-sum">{{ t('Eine Frage zu diesem Formular?') }}</summary>
        <form class="ask-in" novalidate @submit.prevent="ask">
          <div class="field">
            <label class="q-l" for="wz-ask">{{ t('Ihre Frage') }}</label>
            <textarea id="wz-ask" v-model="askText" class="input" rows="2" maxlength="500" aria-describedby="wz-ask-h"></textarea>
            <p id="wz-ask-h" class="hint">{{ t('Zum Ausfüllen dieses Formulars. Fragen zu Krankheiten beantwortet der Lotse nicht. Schreiben Sie keine Namen oder Nummern hinein.') }}</p>
          </div>
          <div class="actions"><button type="submit" class="btn btn-secondary" :aria-disabled="asked?.state === 'loading'">{{ t('Fragen') }}</button></div>
          <div v-if="asked" class="answer" role="status">
            <p v-if="asked.state === 'loading'" class="hint">{{ t('Einen Moment …') }}</p>
            <p v-else-if="asked.state === 'fail'">{{ t('Eine Antwort ist gerade nicht möglich. Bei Fragen hilft die Stelle, an die der Antrag geht.') }}</p>
            <p v-else-if="asked.refused">{{ t('Fragen zu Krankheiten, Beschwerden oder Medikamenten beantwortet der Lotse nicht. Diese Angaben tragen Sie selbst ins Formular ein.') }}</p>
            <template v-else>
              <p>{{ asked.text }}</p>
              <p class="hint">{{ t('Antwort der KI. Es gilt, was im Formular steht.') }}</p>
            </template>
          </div>
        </form>
      </details>
    </div>

    <footer class="wz-foot">
      <template v-if="confirmClose">
        <p class="confirm" role="alert">{{ t('Ihre Änderungen auf dieser Seite sind noch nicht gespeichert.') }}</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" @click="saveAndClose">{{ t('Speichern und schließen') }}</button>
          <button type="button" class="btn btn-secondary" @click="discard">{{ t('Verwerfen') }}</button>
          <button type="button" class="btn btn-quiet" @click="confirmClose = false">{{ t('Weiter ausfüllen') }}</button>
        </div>
      </template>
      <template v-else-if="data">
        <p v-if="saveErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ t(saveErr) }}</span></p>
        <button v-if="at > 0" type="button" class="btn btn-secondary" @click="go(at - 1)"><svg class="i flip" aria-hidden="true"><use href="#i-arrow" /></svg>{{ t('Zurück') }}</button>
        <span v-else></span>
        <button v-if="!review" type="button" class="btn btn-primary" :aria-disabled="saving" @click="!saving && go(at + 1)">
          <span>{{ t('Weiter') }}<span class="to-next">: {{ t(stations[at + 1] ?? '') }}</span></span><svg class="i" aria-hidden="true"><use href="#i-arrow" /></svg>
        </button>
      </template>
    </footer>
  </dialog>
</template>

<style scoped>
dialog.wz { width: min(50rem, calc(100% - 2rem)); height: calc(100dvh - 2rem); max-height: none; overflow: hidden; }
dialog.wz[open] { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; }
dialog.wz > * { min-width: 0; }
.wz-head { display: flex; align-items: flex-start; justify-content: space-between; gap: .75rem; padding: 1rem 1rem 0 1.5rem; background: var(--sheet); }
.wz-title { font-size: var(--fs-h3); font-weight: 600; color: var(--head); padding-top: .4rem; }
.prog { border-bottom: var(--hair); }
.wz-sub { display: flex; flex-wrap: wrap; gap: .2rem 1rem; min-height: 1.5em; padding: 0 1.5rem; color: var(--ink-3); font-size: var(--fs-small); }
.saved { display: inline-flex; align-items: center; gap: .3em; }
/* Progress: the plan's wayfinding line, laid down. Done stations are filled with a tick, the current one is a ring
   with a dot, later ones are hollow. */
.rail { list-style: none; margin: 0; padding: .6rem 1.5rem 1rem; display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); }
.rail li { position: relative; display: grid; justify-items: center; }
.rail li::before { content: ""; position: absolute; top: calc(.75rem - 1px); left: -50%; width: 100%; height: 2px; background: var(--rule-2); }
.rail li:first-child::before { display: none; }
.rail li.done::before, .rail li.now::before { background: var(--ready-mark); }
.rail button { position: relative; display: grid; justify-items: center; align-content: start; gap: .3rem; min-height: 2.75rem; padding: 0 .2rem; border: 0; background: none; color: var(--ink-2); font: inherit; font-size: var(--fs-small); font-weight: 600; cursor: pointer; }
.rail button:hover .label { text-decoration: underline; text-underline-offset: .15em; }
.dot { width: 1.5rem; height: 1.5rem; display: grid; place-items: center; border-radius: 50%; border: 2px solid var(--rule-2); background: var(--sheet); color: var(--sheet); }
.done .dot { background: var(--ready-mark); border-color: var(--ready-mark); }
.done .dot .i { width: .85rem; height: .85rem; stroke-width: 3.5; }
.now .dot { border: 3px solid var(--turn-mark); background: var(--turn-mark); box-shadow: inset 0 0 0 4px var(--sheet); }
.now button { color: var(--turn-ink); font-weight: 700; }
.label { line-height: 1.2; hyphens: auto; overflow-wrap: anywhere; }
.rail-now { display: none; }
.wz-body { overflow: auto; padding: 1.5rem 1.5rem 2rem; }
.wz-in, .ask { max-width: 40rem; margin-inline: auto; hyphens: auto; }
.wz-in { display: grid; gap: 1.75rem; }
.wz-in > * { min-width: 0; }
.sec-h { display: grid; gap: .25rem; }
.sec-h h3 { font-size: var(--fs-h2); font-weight: 600; color: var(--head); }
.tr { display: block; font-weight: 400; color: var(--ink-2); }
.q { display: grid; gap: .5rem; }
.q-l { margin: 0; font-weight: 600; line-height: 1.35; }
.q-l .tr { font-size: var(--fs-small); }
.q-help { display: grid; gap: .25rem; margin: 0; }
.src { display: inline-flex; align-items: center; gap: .35em; width: fit-content; color: var(--ready-ink); font-weight: 600; }
.src .i { width: 1em; height: 1em; }
.check small { display: block; }
/* A question that depends on an earlier answer hangs off it, like a branch of the line. */
.follow { margin-left: .7rem; padding-left: 1.25rem; border-left: 2px solid var(--rule-2); }
.follow + .follow { margin-top: -1.75rem; padding-top: 1.75rem; } /* one line through the branch, over the gaps */
.input.short { max-width: 14rem; }
.draft { display: grid; gap: .6rem; }
.suggested textarea { border-style: dashed; border-width: 2px; border-color: var(--wait-mark); }
.q-tools { display: flex; flex-wrap: wrap; align-items: center; gap: 0 1.25rem; }
.q-tools .linkbtn { display: inline-flex; align-items: center; gap: .35em; min-height: 2.75rem; font-weight: 600; text-decoration: none; }
.q-tools .linkbtn:hover span { text-decoration: underline; }
.explain { display: grid; gap: .4rem; padding: .8rem 1rem; border-radius: var(--r-m); background: var(--sunk); }
.who { display: flex; align-items: center; gap: .4em; font-size: var(--fs-small); color: var(--ink-3); }
.err[hidden], .hint[hidden] { display: none; }
.ask { margin-top: 2rem; padding: .25rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.ask[open] { padding-bottom: 1.1rem; }
.more-sum { display: inline-flex; align-items: center; gap: .45em; min-height: 2.75rem; color: var(--head); font-weight: 600; cursor: pointer; list-style: none; }
.more-sum::-webkit-details-marker { display: none; }
.more-sum::after { content: ""; width: .45em; height: .45em; border: solid currentColor; border-width: 0 2px 2px 0; transform: translateY(-.15em) rotate(45deg); }
.ask[open] .more-sum::after { transform: translateY(.1em) rotate(-135deg); }
.ask-in { display: grid; gap: .75rem; margin-top: .5rem; }
.answer { display: grid; gap: .4rem; padding: .8rem 1rem; border-radius: var(--r-m); background: var(--sheet); border: var(--hair); }
/* Review */
.find { display: grid; padding: .3rem 1.1rem .8rem; border: var(--hair); border-radius: var(--r-m); }
.find h4, .block h4 { margin: 0; font-size: var(--fs-h3); font-weight: 600; color: var(--head); }
.find > h4 { padding: .7rem 0 .4rem; }
.find ul { list-style: none; margin: 0; padding: 0; }
.find li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: .3rem .7rem; padding: .6rem 0; border-top: var(--hair); }
.find li .i, .ok .i { color: var(--head); }
.find li.f-missing .i { color: var(--ink); }
.ok { display: flex; align-items: center; gap: .5em; padding: .5rem 0; color: var(--ready-ink); font-weight: 600; }
.ok .i { color: var(--ready-mark); }
.ai-h { display: flex; align-items: center; gap: .4em; margin-top: .4rem; padding-top: .8rem; font-size: var(--fs-small); color: var(--ink-3); font-weight: 600; border-top: var(--hair); }
.find .ai li { border-top: 0; padding-top: .3rem; }
.block { display: grid; gap: .6rem; }
.sum { display: grid; gap: .2rem; }
.sum-h { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding-top: .6rem; border-top: var(--hair); }
.sum-h h5 { margin: 0; font-size: 1rem; }
.sum dl { margin: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr); gap: .25rem 1rem; }
.sum dt { color: var(--ink-3); }
.sum dd { margin: 0; font-weight: 600; white-space: pre-line; }
.sum dd.empty { font-weight: 400; color: var(--ink-3); }
.paper { list-style: none; margin: 0; padding: 0; display: grid; }
.paper li { display: grid; grid-template-columns: 9rem minmax(0, 1fr); gap: .2rem 1rem; padding: .55rem 0; border-top: var(--hair); }
.where { color: var(--ink-3); font-size: var(--fs-small); padding-top: .15em; }
.send { display: grid; gap: .9rem; padding: 1.1rem 1.25rem; border-radius: var(--r-m); background: var(--sunk); }
.to { display: flex; gap: .6rem; align-items: flex-start; }
.to .i { margin-top: .15em; color: var(--head); }
.wz-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .75rem; padding: .9rem 1.5rem; border-top: var(--hair); background: var(--sheet); }
.wz-foot > .err { flex-basis: 100%; }
.confirm { flex-basis: 100%; font-weight: 600; }
.flip { transform: scaleX(-1); }
[data-contrast="high"] :is(.explain, .ask, .send) { box-shadow: inset 0 0 0 1px var(--ink); }

/* Narrow (a phone, or large text on a small screen): the whole dialog scrolls, so the progress line moves away and
   leaves the room to the questions; the title and the buttons stay. */
@container (max-width: 40rem) {
  dialog.wz { width: 100%; max-width: 100%; height: 100dvh; border-radius: 0; margin: 0; }
  dialog.wz[open] { display: block; overflow: auto; }
  .wz-head { position: sticky; top: 0; z-index: 1; padding: .5rem .25rem .5rem 1rem; border-bottom: var(--hair); }
  .wz-title { font-size: var(--fs-lead); }
  .wz-sub { padding: .75rem 1rem 0; }
  .rail { padding: .5rem 1rem .25rem; }
  .label { display: none; }
  .rail-now { display: block; padding: 0 1rem .75rem; font-weight: 700; color: var(--turn-ink); }
  .wz-body { overflow: visible; padding: 1.25rem 1rem 1.5rem; }
  .wz-foot { position: sticky; bottom: 0; padding: .75rem 1rem; }
  .wz-foot > .btn { flex: 1; justify-content: center; padding-inline: .75rem; }
  .to-next { display: none; }
  .paper li, .sum dl { grid-template-columns: minmax(0, 1fr); }
  .sum dd { margin-bottom: .4rem; }
  .find { padding-inline: .9rem; }
  .find li { grid-template-columns: auto minmax(0, 1fr); align-items: start; }
  .find li .i { margin-top: .15em; }
  .find li > .btn { grid-column: 2; justify-self: start; padding-inline: 0; }
}
</style>
