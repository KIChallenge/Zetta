<script setup lang="ts">
import { nextTick, reactive, ref, watch } from 'vue'
import { ApiError, GENERIC, UNREACHABLE, type User } from '../auth'
import { k, t } from '../i18n'
import {
  changePassword, deleteAccount, fmtSvnr, getProfile, LANGS, LENGTHS, saveProfile, svnrDigits, svnrOk, type Profile,
} from '../profile'

type Field = 'full_name' | 'street' | 'postal_code' | 'city' | 'svnr' | 'phone' | 'contact_email'
type Section = 'person' | 'answers' | 'password'

const props = defineProps<{ user: User }>()
const emit = defineEmits<{ expired: []; saved: [profile: Profile]; deleted: [] }>()

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/ // as in AuthCard
const FIELDS: { f: Field; label: string; hint: string; max: number; auto: string; type?: string; mode?: 'numeric'; w?: string }[] = [
  { f: 'full_name', label: k('Vor- und Nachname'), hint: k('So, wie er auf Ihrer e-card steht.'), max: 100, auto: 'name' },
  { f: 'street', label: k('Straße und Hausnummer'), hint: k('Zum Beispiel: Favoritenstraße 12/3'), max: 100, auto: 'street-address' },
  { f: 'postal_code', label: k('PLZ'), hint: k('4 Ziffern'), max: 4, auto: 'postal-code', mode: 'numeric', w: 'plz' },
  { f: 'city', label: k('Ort'), hint: k('Zum Beispiel: Wien'), max: 60, auto: 'address-level2', w: 'ort' },
  { f: 'svnr', label: k('Sozialversicherungsnummer'), hint: k('10 Ziffern, steht auf Ihrer e-card. Zum Beispiel: 1237 010180'), max: 20, auto: 'off', mode: 'numeric' },
  { f: 'phone', label: k('Telefonnummer'), hint: k('Für Rückrufe. Zum Beispiel: +43 660 1234567'), max: 30, auto: 'tel', type: 'tel' },
  { f: 'contact_email', label: k('E-Mail-Adresse für Antworten'), hint: k('Hierher können Ämter und Versicherungen antworten.'), max: 254, auto: 'email', type: 'email' },
]
// Mirrors the backend's validation (schemas.py); every field may stay empty.
const RULES: Partial<Record<Field, (v: string) => string>> = {
  postal_code: (v) => (!v || /^\d{4}$/.test(v) ? '' : t('Die Postleitzahl hat 4 Ziffern, zum Beispiel 1100.')),
  svnr: (v) =>
    !v || svnrOk(v) ? ''
    : /^\d{10}$/.test(svnrDigits(v)) ? t('Diese Nummer gibt es nicht. Bitte vergleichen Sie die Ziffern mit Ihrer e-card.')
    : t('Die Nummer hat 10 Ziffern, zum Beispiel 1237 010180.'),
  phone: (v) => (/^[\d +()-]*$/.test(v) ? '' : t('Bitte nur Ziffern, Leerzeichen und + ( ) - verwenden.')),
  contact_email: (v) => (!v || EMAIL.test(v) ? '' : t('Bitte prüfen Sie die E-Mail-Adresse. Sie sieht so aus: name@beispiel.at')),
}
const TEXT = [['m', k('Normal')], ['l', k('Groß')], ['xl', k('Sehr groß')]] as const
const THEME = [['auto', k('Wie mein Gerät')], ['light', k('Hell')], ['dark', k('Dunkel')]] as const
const CONTRAST = [['normal', k('Standard')], ['high', k('Stark')]] as const
const VIEW_KEY = 'lotse-ansicht' // read by applyView() in index.html

const saved = ref<Profile | null>(null)
const loadErr = ref('')
const person = reactive<Record<Field, string>>({ full_name: '', street: '', postal_code: '', city: '', svnr: '', phone: '', contact_email: '' })
const errors = reactive<Record<Field, string>>({ full_name: '', street: '', postal_code: '', city: '', svnr: '', phone: '', contact_email: '' })
const answers = reactive<Pick<Profile, 'answer_language' | 'answer_length'>>({ answer_language: 'de', answer_length: 'short' })
const msg = reactive<Record<Section, { ok: boolean; text: string } | null>>({ person: null, answers: null, password: null })
const busy = reactive<Record<Section | 'delete', boolean>>({ person: false, answers: false, password: false, delete: false })
const pw = reactive({ current: '', next: '' })
const pwErr = reactive({ current: '', next: '' })
const showPw = ref(false)
const delDlg = ref<HTMLDialogElement>()
const delPw = ref('')
const delErr = ref('')

function stored() {
  try {
    return JSON.parse(localStorage.getItem(VIEW_KEY) ?? '{}') ?? {}
  } catch {
    return {}
  }
}
const view = reactive({ text: 'm', theme: 'auto', contrast: 'normal', motion: false, ...stored() })
watch(view, () => {
  try {
    localStorage.setItem(VIEW_KEY, JSON.stringify(view))
  } catch {
    // Private mode or storage blocked: the view still applies until reload.
  }
  applyView()
})

const focus = (id: string) => nextTick(() => document.getElementById(id)?.focus())

// 401 ends the session everywhere; other errors get our own wording per status.
function fail(e: unknown, byStatus: Record<number, string> = {}) {
  const status = e instanceof ApiError ? e.status : 0
  if (status === 401) emit('expired')
  return t(byStatus[status] ?? ((e as Error).message === UNREACHABLE ? UNREACHABLE : GENERIC))
}

function fill(p: Profile) {
  saved.value = p
  for (const { f } of FIELDS) person[f] = f === 'svnr' ? fmtSvnr(p.svnr) : p[f]
  person.contact_email ||= props.user.email
  answers.answer_language = p.answer_language
  answers.answer_length = p.answer_length
}

async function load() {
  loadErr.value = ''
  try {
    fill(await getProfile())
  } catch (e) {
    loadErr.value = fail(e)
  }
}
load()

const check = (f: Field) => !(errors[f] = RULES[f]?.(person[f].trim()) ?? '')
// Live re-check only once a field has been flagged, as in AuthCard.
const recheck = (f: Field) => errors[f] && check(f)

async function save(section: 'person' | 'answers', changes: Partial<Profile>, ok: string) {
  if (busy[section]) return
  busy[section] = true
  msg[section] = null
  try {
    // Only this section's changes: unsaved edits in the other section stay unsaved.
    const p = await saveProfile({ ...saved.value!, ...changes })
    saved.value = p
    emit('saved', p)
    msg[section] = { ok: true, text: ok }
  } catch (e) {
    msg[section] = { ok: false, text: fail(e, { 422: k('Bitte prüfen Sie Ihre Angaben.') }) }
  }
  busy[section] = false
}

function savePerson() {
  const bad = FIELDS.filter(({ f }) => !check(f))
  if (bad.length) return focus(`p-${bad[0]!.f}`)
  const changes = Object.fromEntries(FIELDS.map(({ f }) => [f, person[f].trim()])) as Record<Field, string>
  changes.svnr = svnrDigits(changes.svnr)
  person.svnr = fmtSvnr(changes.svnr)
  save('person', changes, k('Gespeichert. Der Lotse nutzt die Daten ab Ihrer nächsten Nachricht.'))
}

const saveAnswers = () => save('answers', { ...answers }, k('Gespeichert. Das gilt ab Ihrer nächsten Nachricht.'))

async function savePassword() {
  if (busy.password) return
  msg.password = null
  pwErr.current = pw.current ? '' : t('Bitte geben Sie Ihr aktuelles Passwort ein.')
  pwErr.next = pw.next.length >= 10 ? '' : t('Das neue Passwort braucht mindestens 10 Zeichen.')
  if (pwErr.current || pwErr.next) return focus(pwErr.current ? 'pw-current' : 'pw-next')
  busy.password = true
  try {
    await changePassword(pw.current, pw.next)
    pw.current = pw.next = ''
    msg.password = { ok: true, text: k('Ihr Passwort ist geändert.') }
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) {
      pwErr.current = t('Das aktuelle Passwort stimmt nicht.')
      focus('pw-current')
    } else msg.password = { ok: false, text: fail(e) }
  }
  busy.password = false
}

function openDelete() {
  delPw.value = delErr.value = ''
  delDlg.value?.showModal()
}

async function confirmDelete() {
  if (busy.delete) return
  delErr.value = delPw.value ? '' : t('Bitte geben Sie Ihr Passwort ein.')
  if (delErr.value) return focus('del-pw')
  busy.delete = true
  try {
    await deleteAccount(delPw.value)
    delDlg.value?.close()
    emit('deleted')
  } catch (e) {
    delErr.value = fail(e, { 403: k('Das Passwort stimmt nicht.') })
    focus('del-pw')
  }
  busy.delete = false
}
</script>

<template>
  <section class="settings" aria-labelledby="view-h">
    <h1 id="view-h" tabindex="-1">{{ t('Einstellungen') }}</h1>

    <form class="card" aria-labelledby="h-person" novalidate @submit.prevent="savePerson" @input="msg.person = null">
      <h2 id="h-person">{{ t('Persönliche Daten') }}</h2>
      <p class="intro">
        {{ t('Diese Daten bekommt der Lotse in jedem Gespräch, damit er Anrufe und E-Mails für Sie vorbereiten kann. Alle Angaben sind freiwillig.') }}
      </p>
      <p v-if="loadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ loadErr }}</span></p>
      <button v-if="loadErr" type="button" class="btn btn-secondary" @click="load">{{ t('Nochmal laden') }}</button>
      <p v-else-if="!saved" class="muted">{{ t('Ihre Daten werden geladen …') }}</p>
      <template v-else>
        <div class="fields">
          <div v-for="x in FIELDS" :key="x.f" class="field" :class="x.w">
            <label class="field-l" :for="`p-${x.f}`">{{ t(x.label) }}</label>
            <p :id="`p-${x.f}-hint`" class="hint">{{ t(x.hint) }}</p>
            <input
              :id="`p-${x.f}`"
              v-model="person[x.f]"
              class="input"
              :type="x.type ?? 'text'"
              :inputmode="x.mode"
              :maxlength="x.max"
              :autocomplete="x.auto"
              :aria-invalid="!!errors[x.f]"
              :aria-describedby="`p-${x.f}-hint p-${x.f}-err`"
              @input="recheck(x.f)"
              @blur="person[x.f].trim() && check(x.f)"
            />
            <p v-if="errors[x.f]" :id="`p-${x.f}-err`" class="err">
              <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors[x.f] }}</span>
            </p>
          </div>
        </div>
        <div class="foot">
          <button type="submit" class="btn btn-primary" :aria-disabled="busy.person">{{ busy.person ? t('Einen Moment …') : t('Daten speichern') }}</button>
          <p class="msg" :class="{ ok: msg.person?.ok }" role="status">
            <template v-if="msg.person"><svg class="i" aria-hidden="true"><use :href="msg.person.ok ? '#i-check' : '#i-alert'" /></svg><span>{{ t(msg.person.text) }}</span></template>
          </p>
        </div>
      </template>
    </form>

    <form v-if="saved" class="card" aria-labelledby="h-answers" @submit.prevent="saveAnswers" @change="msg.answers = null">
      <h2 id="h-answers">{{ t('So antwortet der Lotse') }}</h2>
      <div class="field">
        <label class="field-l" for="a-lang">{{ t('Sprache') }}</label>
        <select id="a-lang" v-model="answers.answer_language">
          <option v-for="(name, code) in LANGS" :key="code" :value="code">{{ name }}</option>
        </select>
      </div>
      <fieldset>
        <legend>{{ t('Länge der Antworten') }}</legend>
        <div class="seg">
          <label v-for="(label, v) in LENGTHS" :key="v" class="opt">
            <input v-model="answers.answer_length" type="radio" name="answer_length" :value="v" /><span>{{ t(label) }}</span>
          </label>
        </div>
      </fieldset>
      <div class="foot">
        <button type="submit" class="btn btn-primary" :aria-disabled="busy.answers">{{ busy.answers ? t('Einen Moment …') : t('Speichern') }}</button>
        <p class="msg" :class="{ ok: msg.answers?.ok }" role="status">
          <template v-if="msg.answers"><svg class="i" aria-hidden="true"><use :href="msg.answers.ok ? '#i-check' : '#i-alert'" /></svg><span>{{ t(msg.answers.text) }}</span></template>
        </p>
      </div>
    </form>

    <section class="card" aria-labelledby="h-view">
      <h2 id="h-view">{{ t('Ansicht') }}</h2>
      <p class="intro">{{ t('Änderungen gelten sofort und werden auf diesem Gerät gespeichert.') }}</p>
      <fieldset>
        <legend>{{ t('Schriftgröße') }}</legend>
        <div class="seg">
          <label v-for="[v, label] in TEXT" :key="v" class="opt">
            <input v-model="view.text" type="radio" name="text" :value="v" /><span :class="`t-${v}`">{{ t(label) }}</span>
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>{{ t('Farben') }}</legend>
        <div class="seg">
          <label v-for="[v, label] in THEME" :key="v" class="opt">
            <input v-model="view.theme" type="radio" name="theme" :value="v" /><span>{{ t(label) }}</span>
          </label>
        </div>
      </fieldset>
      <fieldset>
        <legend>{{ t('Kontrast') }}</legend>
        <div class="seg">
          <label v-for="[v, label] in CONTRAST" :key="v" class="opt">
            <input v-model="view.contrast" type="radio" name="contrast" :value="v" /><span>{{ t(label) }}</span>
          </label>
        </div>
      </fieldset>
      <label class="toggle">
        <input v-model="view.motion" type="checkbox" /><span><b>{{ t('Weniger Bewegung') }}</b><small>{{ t('Schaltet Animationen aus.') }}</small></span>
      </label>
    </section>

    <form class="card" aria-labelledby="h-pw" novalidate @submit.prevent="savePassword" @input="msg.password = null">
      <h2 id="h-pw">{{ t('Passwort ändern') }}</h2>
      <!-- For password managers: which account this password belongs to. -->
      <input type="email" autocomplete="username" :value="user.email" hidden readonly />
      <div class="field">
        <label class="field-l" for="pw-current">{{ t('Aktuelles Passwort') }}</label>
        <input
          id="pw-current"
          v-model="pw.current"
          class="input"
          :type="showPw ? 'text' : 'password'"
          maxlength="128"
          autocomplete="current-password"
          :aria-invalid="!!pwErr.current"
          aria-describedby="pw-current-err"
          @input="pwErr.current = ''"
        />
        <p v-if="pwErr.current" id="pw-current-err" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ pwErr.current }}</span></p>
      </div>
      <div class="field">
        <label class="field-l" for="pw-next">{{ t('Neues Passwort') }}</label>
        <input
          id="pw-next"
          v-model="pw.next"
          class="input"
          :type="showPw ? 'text' : 'password'"
          maxlength="128"
          autocomplete="new-password"
          :aria-invalid="!!pwErr.next"
          aria-describedby="pw-rule pw-next-err"
          @input="pwErr.next && pw.next.length >= 10 && (pwErr.next = '')"
        />
        <p id="pw-rule" class="hint pw-rule" :class="{ ok: pw.next.length >= 10 }">
          <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Mindestens 10 Zeichen') }}
        </p>
        <p v-if="pwErr.next" id="pw-next-err" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ pwErr.next }}</span></p>
      </div>
      <button type="button" class="btn btn-quiet show-pw" aria-controls="pw-current pw-next" :aria-pressed="showPw" @click="showPw = !showPw">
        <svg class="i" aria-hidden="true"><use href="#i-eye" /></svg>{{ t('Passwörter anzeigen') }}
      </button>
      <div class="foot">
        <button type="submit" class="btn btn-primary" :aria-disabled="busy.password">{{ busy.password ? t('Einen Moment …') : t('Passwort ändern') }}</button>
        <p class="msg" :class="{ ok: msg.password?.ok }" role="status">
          <template v-if="msg.password"><svg class="i" aria-hidden="true"><use :href="msg.password.ok ? '#i-check' : '#i-alert'" /></svg><span>{{ t(msg.password.text) }}</span></template>
        </p>
      </div>
    </form>

    <section class="card danger-zone" aria-labelledby="h-del">
      <h2 id="h-del">{{ t('Konto löschen') }}</h2>
      <p>{{ t('Ihr Konto, Ihre persönlichen Daten und alle Gespräche werden endgültig gelöscht. Das lässt sich nicht rückgängig machen.') }}</p>
      <button type="button" class="btn btn-secondary danger-btn" @click="openDelete">
        <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>{{ t('Konto löschen …') }}
      </button>
    </section>

    <dialog ref="delDlg" aria-labelledby="dd-h" aria-describedby="dd-d">
      <form novalidate @submit.prevent="confirmDelete">
        <div class="dlg-head">
          <h2 id="dd-h">{{ t('Konto löschen?') }}</h2>
          <button type="button" class="btn btn-quiet icon-only" :aria-label="t('Schließen')" @click="delDlg?.close()">
            <svg class="i" aria-hidden="true"><use href="#i-x" /></svg>
          </button>
        </div>
        <div class="dlg-body">
          <p id="dd-d"><b>{{ user.email }}</b>: {{ t('Ihr Konto, Ihre persönlichen Daten und alle Gespräche werden endgültig gelöscht. Das lässt sich nicht rückgängig machen.') }}</p>
          <input type="email" autocomplete="username" :value="user.email" hidden readonly />
          <div class="field">
            <label class="field-l" for="del-pw">{{ t('Zur Sicherheit: Ihr Passwort') }}</label>
            <input
              id="del-pw"
              v-model="delPw"
              class="input"
              type="password"
              maxlength="128"
              autocomplete="current-password"
              autofocus
              :aria-invalid="!!delErr"
              aria-describedby="del-err"
              @input="delErr = ''"
            />
            <p v-if="delErr" id="del-err" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ delErr }}</span></p>
          </div>
        </div>
        <div class="dlg-foot">
          <button type="button" class="btn btn-secondary" @click="delDlg?.close()">{{ t('Abbrechen') }}</button>
          <button type="submit" class="btn btn-danger" :aria-disabled="busy.delete">
            <svg class="i" aria-hidden="true"><use href="#i-trash" /></svg>{{ busy.delete ? t('Einen Moment …') : t('Endgültig löschen') }}
          </button>
        </div>
      </form>
    </dialog>
  </section>
</template>

<style scoped>
/* Scrolls inside the main pane; the window itself never scrolls. */
.settings {
  --gut: max(clamp(.75rem, 4vw, 1.25rem), calc((100% - 42rem) / 2));
  min-width: 0; min-height: 0; overflow-y: auto;
  display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: 1.5rem;
  padding: clamp(1.5rem, 5vh, 2.75rem) var(--gut) 3rem;
}
.settings > h1 { font-size: clamp(var(--fs-h2), 5cqi, var(--fs-h1)); }
.card { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1.1rem; padding: 1.35rem clamp(.9rem, 4vw, 1.5rem) 1.5rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
.card h2 { font-size: var(--fs-h3); font-weight: 600; color: var(--head); }
.intro { color: var(--ink-2); }
.fields { display: flex; flex-wrap: wrap; gap: 1.1rem 1rem; }
.fields .field { flex: 1 1 100%; min-width: 0; }
.fields .plz { flex: 1 1 6rem; }
.fields .ort { flex: 3 1 12rem; }
.field .hint { margin-top: -.2rem; }
.foot { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1rem; }
.msg { display: flex; gap: .4em; align-items: flex-start; font-weight: 600; color: var(--danger); }
.msg.ok { color: var(--ready-ink); }
.msg .i { margin-top: .15em; }

select { width: 100%; max-width: 24rem; min-height: 3rem; padding: .4rem 1.1rem; font: inherit; color: var(--ink); background: var(--sheet); border: 1px solid var(--rule-2); border-radius: var(--r-pill); }
select:hover { border-color: var(--action); }
select:focus-visible { border-color: var(--action); outline-offset: 2px; }
[data-contrast="high"] select { border-width: 2px; }
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
legend { padding: 0; margin-bottom: .5rem; font-weight: 600; }
.seg { display: flex; flex-wrap: wrap; gap: .5rem; }
.opt { display: inline-flex; align-items: center; gap: .6rem; min-height: 2.9rem; padding: .45rem 1.2rem .45rem 1rem; border-radius: var(--r-pill); border: 1px solid var(--rule-2); cursor: pointer; font-weight: 600; transition: background-color .15s, border-color .15s; }
.opt:hover { border-color: var(--action); }
.opt:has(input:checked) { border-color: var(--action); background: var(--band); color: var(--head); }
.opt:has(input:focus-visible) { outline: 3px solid var(--focus); outline-offset: 2px; }
.opt input:focus-visible { outline: none; }
[data-contrast="high"] .opt { border-width: 2px; }
.opt input, .toggle input { width: 1.25rem; height: 1.25rem; margin: 0; flex: none; accent-color: var(--action); }
.t-l { font-size: 1.15rem; }
.t-xl { font-size: 1.3rem; }
.toggle { display: flex; align-items: flex-start; gap: .85rem; cursor: pointer; }
.toggle input { margin-top: .15rem; }
.toggle b { display: block; }
.toggle small { display: block; font-size: var(--fs-small); color: var(--ink-3); }

.show-pw { justify-self: start; }
.pw-rule { display: flex; gap: .4em; align-items: center; }
.pw-rule.ok { color: var(--ready-ink); }
.pw-rule .i { width: 1.05em; height: 1.05em; }

.danger-zone { border-color: color-mix(in srgb, var(--danger) 55%, transparent); }
[data-contrast="high"] .danger-zone { border-color: var(--danger); }
.danger-zone h2 { color: var(--danger); }
.danger-btn { justify-self: start; color: var(--danger); }
.danger-btn:hover { background: color-mix(in srgb, var(--danger) 10%, var(--sheet)); }
</style>
