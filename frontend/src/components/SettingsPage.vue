<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { ApiError, GENERIC, TOO_MANY, UNREACHABLE, type User } from '../auth'
import { fmtDate, fmtPhone, fmtSvnr, joinSvnr, realDate, splitSvnr, svnrDigits, svnrOk, VIENNA } from '../fields'
import { k, t } from '../i18n'
import { view } from '../view'
import DetailInputs from './DetailInputs.vue'
import {
  changePassword, deleteAccount, deletePerson, getPeople, getProfile, LANGS, LENGTHS, savePerson, saveProfile, type KeptPerson,
  type Profile,
} from '../profile'

type Field = 'full_name' | 'street' | 'postal_code' | 'city' | 'phone' | 'contact_email'
type Key = Field | 'svnr'

const props = defineProps<{ user: User }>()
const emit = defineEmits<{ expired: []; saved: [profile: Profile]; deleted: [] }>()

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/ // as in AuthCard
const KEYS = ['full_name', 'street', 'postal_code', 'city', 'phone', 'contact_email'] as const
const CONTACT: { f: Field; label: string; max: number; auto: string; type?: string; mode?: 'numeric'; w?: string }[] = [
  { f: 'street', label: k('Straße und Hausnummer'), max: 100, auto: 'street-address' },
  { f: 'postal_code', label: k('PLZ'), max: 4, auto: 'postal-code', mode: 'numeric', w: 'plz' },
  { f: 'city', label: k('Ort'), max: 60, auto: 'address-level2', w: 'ort' },
  { f: 'phone', label: k('Telefonnummer'), max: 30, auto: 'tel', type: 'tel' },
  { f: 'contact_email', label: k('E-Mail-Adresse für Antworten'), max: 254, auto: 'email', type: 'email' },
]
// Mirrors the backend's validation (schemas.py); every field may stay empty. Fields with a rule get a ✓ once it passes.
const RULES: Partial<Record<Field, (v: string) => string>> = {
  postal_code: (v) => (!v || /^\d{4}$/.test(v) ? '' : t('Die Postleitzahl hat 4 Ziffern, zum Beispiel 1100.')),
  contact_email: (v) => (!v || EMAIL.test(v) ? '' : t('Bitte prüfen Sie die E-Mail-Adresse. Sie sieht so aus: name@beispiel.at')),
}
const NO_SVNR = k('Diese Nummer gibt es nicht. Bitte vergleichen Sie die Ziffern mit Ihrer e-card.')
const TEXT = [['m', k('Normal')], ['l', k('Groß')], ['xl', k('Sehr groß')]] as const
const THEME = [['auto', k('Wie mein Gerät')], ['light', k('Hell')], ['dark', k('Dunkel')]] as const
const CONTRAST = [['normal', k('Standard')], ['high', k('Stark')]] as const

const saved = ref<Profile | null>(null)
const loadErr = ref('')
const saveErr = ref('')
const person = reactive<Record<Field, string>>({ full_name: '', street: '', postal_code: '', city: '', phone: '', contact_email: '' })
// The SVNR is entered as on the e-card: 4 digits, then the birth date; "Nummer weicht ab?" switches to the whole number.
const sv = reactive({ birth: '', serial: '', whole: '', own: false })
const errors = reactive<Record<Key, string>>({ full_name: '', street: '', postal_code: '', city: '', svnr: '', phone: '', contact_email: '' })
const answers = reactive<Pick<Profile, 'answer_language' | 'answer_length' | 'phone_calls'>>({ answer_language: 'de', answer_length: 'short', phone_calls: true })
const busy = reactive({ data: false, password: false, delete: false })
const pw = reactive({ current: '', next: '' })
const pwErr = reactive({ current: '', next: '' })
const pwMsg = ref<{ ok: boolean; text: string } | null>(null)
const showPw = ref(false)
const svBox = ref<HTMLFieldSetElement>()
const delDlg = ref<HTMLDialogElement>()
const delPw = ref('')
const delErr = ref('')

const svnr = computed(() => (sv.own ? svnrDigits(sv.whole) : joinSvnr(sv.serial, sv.birth)))
const draft = computed<Profile>(() => ({
  ...(Object.fromEntries(KEYS.map((f) => [f, person[f].trim()])) as Record<Field, string>),
  svnr: svnr.value,
  ...answers,
}))
const dirty = computed(() => !!saved.value && (Object.keys(draft.value) as (keyof Profile)[]).some((f) => draft.value[f] !== saved.value![f]))

const focus = (id: string) => nextTick(() => document.getElementById(id)?.focus())

// 401 ends the session everywhere; other errors get our own wording per status.
function fail(e: unknown, byStatus: Record<number, string> = {}) {
  const status = e instanceof ApiError ? e.status : 0
  if (status === 401) emit('expired')
  return t(byStatus[status] ?? (status === 429 ? TOO_MANY : (e as Error).message === UNREACHABLE ? UNREACHABLE : GENERIC))
}

function fill(p: Profile) {
  saved.value = p
  for (const f of KEYS) person[f] = p[f]
  person.contact_email ||= props.user.email
  const parts = splitSvnr(p.svnr)
  Object.assign(sv, { serial: parts?.serial ?? '', birth: parts?.birth ?? '', whole: fmtSvnr(p.svnr), own: !!p.svnr && !parts })
  answers.answer_language = p.answer_language
  answers.answer_length = p.answer_length
  answers.phone_calls = p.phone_calls
}

async function load() {
  loadErr.value = ''
  try {
    const [profile, kept] = await Promise.all([getProfile(), getPeople()])
    fill(profile)
    people.value = kept
  } catch (e) {
    loadErr.value = fail(e)
  }
}

// Details for application forms, per person: entered here ahead of time or learned from form cards.
const people = ref<KeptPerson[]>([])
const peopleErr = ref('')
const editing = ref<string | null>(null) // the relation whose details are open for editing
const confirming = ref<string | null>(null) // the relation whose delete waits for a "yes"
const adding = ref('')
const editor = ref<InstanceType<typeof DetailInputs>[]>([]) // a ref in v-for is a list; one editor is open at most
const shownPeople = computed(() => people.value.filter((p) => p.kept || p.relation === editing.value))
const addable = computed(() => people.value.filter((p) => !p.kept && p.relation !== editing.value))

function startAdd() {
  editing.value = adding.value || addable.value[0]!.relation
  adding.value = ''
  focus('h-kept-edit')
}

async function savePeople(relation: string) {
  const entered = editor.value[0]?.collect()
  if (!entered) return
  peopleErr.value = ''
  try {
    const next = await savePerson(relation, entered[relation] ?? {})
    people.value = people.value.map((p) => (p.relation === relation ? next : p))
    editing.value = null
  } catch (e) {
    peopleErr.value = fail(e)
  }
}

async function forget(relation: string) {
  peopleErr.value = ''
  try {
    await deletePerson(relation)
    people.value = await getPeople()
    confirming.value = null
  } catch (e) {
    peopleErr.value = fail(e)
  }
}

load()

function rule(f: Key) {
  if (f !== 'svnr') return RULES[f]?.(person[f].trim()) ?? ''
  const d = svnr.value
  if (sv.own) return !d || svnrOk(d) ? '' : d.length === 10 ? t(NO_SVNR) : t('Die Nummer hat 10 Ziffern, zum Beispiel 1237 010180.')
  if (!sv.serial && !sv.birth) return ''
  if (sv.birth.length === 10 && !realDate(sv.birth)) return t('Bitte prüfen Sie das Geburtsdatum.')
  return !d ? t('Bitte geben Sie das Geburtsdatum und alle 4 Ziffern ein.') : svnrOk(d) ? '' : t(NO_SVNR)
}
const check = (f: Key) => !(errors[f] = rule(f))
// Live re-check only once a field has been flagged, as in AuthCard.
const recheck = (f: Key) => errors[f] && check(f)
const ok = (f: Field) => !!RULES[f] && !!person[f].trim() && !RULES[f]!(person[f].trim())

function onInput(f: Field) {
  if (f === 'postal_code') {
    person.postal_code = person.postal_code.replace(/\D/g, '')
    if (VIENNA.test(person.postal_code) && !person.city.trim()) person.city = 'Wien'
  }
  if (f === 'phone') person.phone = fmtPhone(person.phone)
  recheck(f)
}

function onBirth() {
  sv.birth = fmtDate(sv.birth)
  recheck('svnr')
}

function onSerial() {
  const d = sv.serial.replace(/\D/g, '')
  if (d.length < 10) {
    sv.serial = d.slice(0, 4)
    // 4 digits typed: on to the date, as on the e-card, but only while it is empty.
    if (sv.serial.length === 4 && !sv.birth) focus('p-birth')
  } else {
    // A pasted whole number: split it, or keep it whole if its date part is no birth date.
    const parts = splitSvnr(d.slice(0, 10))
    if (parts) Object.assign(sv, parts)
    else {
      Object.assign(sv, { own: true, whole: fmtSvnr(d.slice(0, 10)) })
      focus('p-svnr')
    }
  }
  recheck('svnr')
}

function toggleOwn() {
  const parts = splitSvnr(svnrDigits(sv.whole))
  if (!sv.own) sv.whole = fmtSvnr(joinSvnr(sv.serial, sv.birth) || sv.serial)
  else if (parts) Object.assign(sv, parts)
  sv.own = !sv.own
  errors.svnr = ''
  focus(sv.own ? 'p-svnr' : 'p-serial')
}

// Check the SVNR once focus leaves its group, not when moving from the date to the digits.
const leaveSvnr = (e: FocusEvent) => svBox.value?.contains(e.relatedTarget as Node) || check('svnr')
// The boxes hide the real input, so typing always goes to the end. Deferred: browsers select all after a Tab focus.
function caretToEnd(e: Event) {
  const el = e.target as HTMLInputElement
  setTimeout(() => el.setSelectionRange(99, 99))
}

async function save() {
  if (busy.data || !dirty.value) return
  const bad = (['full_name', 'svnr', ...KEYS] as Key[]).filter((f) => !check(f))
  if (bad.length) return focus(bad[0] === 'svnr' ? (sv.own ? 'p-svnr' : 'p-serial') : `p-${bad[0]}`)
  busy.data = true
  saveErr.value = ''
  try {
    saved.value = await saveProfile(draft.value)
    emit('saved', saved.value)
  } catch (e) {
    saveErr.value = fail(e, { 422: k('Bitte prüfen Sie Ihre Angaben.') })
  }
  busy.data = false
}

async function savePassword() {
  if (busy.password) return
  pwMsg.value = null
  pwErr.current = pw.current ? '' : t('Bitte geben Sie Ihr aktuelles Passwort ein.')
  pwErr.next = pw.next.length >= 10 ? '' : t('Das neue Passwort braucht mindestens 10 Zeichen.')
  if (pwErr.current || pwErr.next) return focus(pwErr.current ? 'pw-current' : 'pw-next')
  busy.password = true
  try {
    await changePassword(pw.current, pw.next)
    pw.current = pw.next = ''
    pwMsg.value = { ok: true, text: k('Ihr Passwort ist geändert.') }
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) {
      pwErr.current = t('Das aktuelle Passwort stimmt nicht.')
      focus('pw-current')
    } else pwMsg.value = { ok: false, text: fail(e) }
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
    <header class="head">
      <h1 id="view-h" tabindex="-1">{{ t('Einstellungen') }}</h1>
      <p class="intro">{{ t('Zetta setzt Ihre Angaben in Anrufe und E-Mails ein. Alles ist freiwillig.') }}</p>
    </header>

    <p v-if="loadErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ loadErr }}</span></p>
    <button v-if="loadErr" type="button" class="btn btn-secondary again" @click="load">{{ t('Nochmal laden') }}</button>
    <p v-else-if="!saved" class="muted">{{ t('Ihre Daten werden geladen …') }}</p>

    <form v-else class="grid" novalidate @submit.prevent="save" @input="saveErr = ''">
      <section class="card" aria-labelledby="h-person">
        <h2 id="h-person">{{ t('Person') }}</h2>
        <div class="field">
          <label class="field-l" for="p-full_name">{{ t('Vor- und Nachname') }}</label>
          <input id="p-full_name" v-model="person.full_name" class="input" maxlength="100" autocomplete="name" />
        </div>
        <fieldset ref="svBox" class="svnr" @focusout="leaveSvnr">
          <legend class="field-l">{{ t('Sozialversicherungsnummer') }}</legend>
          <div v-if="!sv.own" class="sv-row">
            <div class="field">
              <label class="sub-l" for="p-serial">{{ t('Erste 4 Ziffern') }}</label>
              <div class="code">
                <span v-for="i in 4" :key="i" class="cell" :class="{ at: i === Math.min(sv.serial.length + 1, 4) }" aria-hidden="true">{{ sv.serial[i - 1] }}</span>
                <input
                  id="p-serial"
                  v-model="sv.serial"
                  inputmode="numeric"
                  autocomplete="off"
                  :aria-invalid="!!errors.svnr"
                  aria-describedby="sv-out"
                  @input="onSerial"
                  @focus="caretToEnd"
                  @click="caretToEnd"
                />
              </div>
            </div>
            <div class="field">
              <label class="sub-l" for="p-birth">{{ t('Geburtsdatum') }}</label>
              <input
                id="p-birth"
                v-model="sv.birth"
                class="input date"
                inputmode="numeric"
                maxlength="10"
                :placeholder="t('TT.MM.JJJJ')"
                autocomplete="bday"
                :aria-invalid="!!errors.svnr"
                aria-describedby="sv-out"
                @input="onBirth"
              />
            </div>
          </div>
          <input
            v-else
            id="p-svnr"
            v-model="sv.whole"
            class="input whole"
            inputmode="numeric"
            maxlength="11"
            autocomplete="off"
            :aria-label="t('Sozialversicherungsnummer')"
            :aria-invalid="!!errors.svnr"
            aria-describedby="sv-out"
            @input="sv.whole = fmtSvnr(sv.whole.replace(/\D/g, '').slice(0, 10)); recheck('svnr')"
          />
          <div class="sv-foot">
            <div id="sv-out" role="status">
              <p v-if="errors.svnr" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors.svnr }}</span></p>
              <p v-else-if="svnrOk(svnr)" class="good"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ fmtSvnr(svnr) }}</p>
            </div>
            <button type="button" class="linkbtn" @click="toggleOwn">{{ sv.own ? t('Mit Geburtsdatum eingeben') : t('Nummer weicht ab?') }}</button>
          </div>
        </fieldset>
      </section>

      <section class="card" aria-labelledby="h-contact">
        <h2 id="h-contact">{{ t('Kontakt') }}</h2>
        <div class="fields">
          <div v-for="x in CONTACT" :key="x.f" class="field" :class="x.w">
            <label class="field-l" :for="`p-${x.f}`">{{ t(x.label) }}</label>
            <div class="in">
              <input
                :id="`p-${x.f}`"
                v-model="person[x.f]"
                class="input"
                :type="x.type ?? 'text'"
                :inputmode="x.mode"
                :maxlength="x.max"
                :autocomplete="x.auto"
                :aria-invalid="!!errors[x.f]"
                :aria-describedby="`p-${x.f}-err`"
                @input="onInput(x.f)"
                @blur="person[x.f].trim() && check(x.f)"
              />
              <svg v-if="ok(x.f)" class="i good" aria-hidden="true"><use href="#i-check" /></svg>
            </div>
            <p v-if="errors[x.f]" :id="`p-${x.f}-err`" class="err">
              <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors[x.f] }}</span>
            </p>
          </div>
        </div>
      </section>

      <section class="card wide" aria-labelledby="h-answers">
        <h2 id="h-answers">{{ t('So antwortet Zetta') }}</h2>
        <div class="row">
          <div class="field">
            <label class="field-l" for="a-lang">{{ t('Sprache') }}</label>
            <select id="a-lang" v-model="answers.answer_language">
              <option v-for="(name, code) in LANGS" :key="code" :value="code">{{ name }}</option>
            </select>
          </div>
          <fieldset>
            <legend class="field-l">{{ t('Länge der Antworten') }}</legend>
            <div class="seg">
              <label v-for="(label, v) in LENGTHS" :key="v" class="opt">
                <input v-model="answers.answer_length" type="radio" name="answer_length" :value="v" /><span>{{ t(label) }}</span>
              </label>
            </div>
          </fieldset>
          <div class="field">
            <label class="toggle"><input v-model="answers.phone_calls" type="checkbox" aria-describedby="a-phone-d" /><b>{{ t('Anrufe vorschlagen') }}</b></label>
            <p id="a-phone-d" class="hint">{{ t('Ausgeschaltet schlägt Zetta, wo es geht, eine E-Mail statt eines Anrufs vor. Gilt ab dem nächsten Plan.') }}</p>
          </div>
        </div>
      </section>

      <div class="savebar" :class="{ stick: dirty }">
        <div role="status">
          <p v-if="saveErr" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ saveErr }}</span></p>
          <p v-else-if="dirty" class="pill" data-tone="turn">{{ t('Nicht gespeichert') }}</p>
          <p v-else class="muted done"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Alles gespeichert') }}</p>
        </div>
        <button type="submit" class="btn btn-primary" :disabled="!dirty" :aria-disabled="busy.data">{{ busy.data ? t('Einen Moment …') : t('Speichern') }}</button>
      </div>
    </form>

    <section v-if="saved" class="card" aria-labelledby="h-kept">
      <div class="card-h">
        <h2 id="h-kept">{{ t('Angaben für Anträge') }}</h2>
        <p class="hint">{{ t('Tragen Sie hier ein, was Sie schon wissen. Den Rest fragt Zetta beim ersten Formular und merkt es sich.') }}</p>
      </div>
      <p v-if="!shownPeople.length" class="muted">{{ t('Noch nichts gemerkt.') }}</p>
      <div v-for="p in shownPeople" :key="p.relation" class="kept">
        <div class="card-h">
          <p :id="editing === p.relation ? 'h-kept-edit' : undefined" class="mini-h" tabindex="-1">{{ t(p.label) }}</p>
          <div v-if="editing !== p.relation" class="kept-actions">
            <template v-if="confirming === p.relation">
              <span role="status">{{ t('Wirklich löschen?') }}</span>
              <button type="button" class="btn btn-quiet danger" @click="forget(p.relation)">{{ t('Ja, löschen') }}</button>
              <button type="button" class="btn btn-quiet" @click="confirming = null">{{ t('Abbrechen') }}</button>
            </template>
            <template v-else>
              <button type="button" class="btn btn-quiet" :aria-label="t('Angaben bearbeiten: {name}', { name: t(p.label) })" @click="editing = p.relation; confirming = null">{{ t('Bearbeiten') }}</button>
              <button type="button" class="btn btn-quiet danger" :aria-label="t('Angaben löschen: {name}', { name: t(p.label) })" @click="confirming = p.relation">{{ t('Löschen') }}</button>
            </template>
          </div>
        </div>
        <form v-if="editing === p.relation" class="kept-edit" novalidate @submit.prevent="savePeople(p.relation)">
          <DetailInputs ref="editor" :entries="p.entries" :scope="p.relation" :own="p.relation === 'self'" />
          <div class="kept-actions">
            <button type="submit" class="btn btn-primary">{{ t('Speichern') }}</button>
            <button type="button" class="btn btn-quiet" @click="editing = null">{{ t('Abbrechen') }}</button>
          </div>
        </form>
        <dl v-else class="kept-list">
          <template v-for="d in p.entries.filter((x) => x.shown)" :key="d.entry"><dt>{{ t(d.label) }}</dt><dd>{{ t(d.shown) }}</dd></template>
        </dl>
      </div>
      <div v-if="addable.length && !editing" class="kept-add">
        <label class="field-l" for="k-add">{{ t('Angaben eintragen für') }}</label>
        <div class="kept-actions">
          <select id="k-add" v-model="adding">
            <option value="" disabled>{{ t('Bitte wählen') }}</option>
            <option v-for="p in addable" :key="p.relation" :value="p.relation">{{ t(p.label) }}</option>
          </select>
          <button type="button" class="btn btn-secondary" :disabled="!adding" @click="startAdd">{{ t('Eintragen') }}</button>
        </div>
      </div>
      <p v-if="peopleErr" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ peopleErr }}</span></p>
    </section>

    <section class="card" aria-labelledby="h-view">
      <div class="card-h">
        <h2 id="h-view">{{ t('Ansicht') }}</h2>
        <p class="hint">{{ t('Gilt sofort auf diesem Gerät.') }}</p>
      </div>
      <div class="row view">
        <fieldset>
          <legend class="field-l">{{ t('Schriftgröße') }}</legend>
          <div class="seg">
            <label v-for="[v, label] in TEXT" :key="v" class="opt">
              <input v-model="view.text" type="radio" name="text" :value="v" /><span :class="`t-${v}`">{{ t(label) }}</span>
            </label>
          </div>
        </fieldset>
        <fieldset>
          <legend class="field-l">{{ t('Kontrast') }}</legend>
          <div class="seg">
            <label v-for="[v, label] in CONTRAST" :key="v" class="opt">
              <input v-model="view.contrast" type="radio" name="contrast" :value="v" /><span>{{ t(label) }}</span>
            </label>
          </div>
        </fieldset>
        <fieldset>
          <legend class="field-l">{{ t('Farben') }}</legend>
          <div class="seg">
            <label v-for="[v, label] in THEME" :key="v" class="opt">
              <input v-model="view.theme" type="radio" name="theme" :value="v" /><span>{{ t(label) }}</span>
            </label>
          </div>
        </fieldset>
        <label class="toggle"><input v-model="view.motion" type="checkbox" /><b>{{ t('Weniger Bewegung') }}</b></label>
      </div>
    </section>

    <section class="card sec" aria-labelledby="h-sec">
      <h2 id="h-sec">{{ t('Sicherheit') }}</h2>
      <details class="more">
        <summary>{{ t('Passwort ändern') }}</summary>
        <form class="pw" novalidate @submit.prevent="savePassword" @input="pwMsg = null">
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
          <div class="actions">
            <button type="submit" class="btn btn-primary" :aria-disabled="busy.password">{{ busy.password ? t('Einen Moment …') : t('Passwort ändern') }}</button>
            <button type="button" class="btn btn-quiet" aria-controls="pw-current pw-next" :aria-pressed="showPw" @click="showPw = !showPw">
              <svg class="i" aria-hidden="true"><use href="#i-eye" /></svg>{{ t('Passwörter anzeigen') }}
            </button>
          </div>
          <p class="msg" :class="{ ok: pwMsg?.ok }" role="status">
            <template v-if="pwMsg"><svg class="i" aria-hidden="true"><use :href="pwMsg.ok ? '#i-check' : '#i-alert'" /></svg><span>{{ t(pwMsg.text) }}</span></template>
          </p>
        </form>
      </details>
      <button type="button" class="btn btn-quiet danger del" @click="openDelete">
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
/* Scrolls inside the main pane; the window itself never scrolls. Two columns once there is room (in rem, so text size counts). */
.settings {
  container: settings / inline-size;
  --gut: max(clamp(.75rem, 4vw, 1.25rem), calc((100% - 62rem) / 2));
  min-width: 0; min-height: 0; overflow-y: auto;
  display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: 1.25rem;
  padding: clamp(1.25rem, 4vh, 2.25rem) var(--gut) 2rem;
}
.head { display: grid; gap: .3rem; }
.head h1 { font-size: clamp(var(--fs-h2), 5cqi, var(--fs-h1)); }
.intro { color: var(--ink-2); }
.again { justify-self: start; }
.grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1.25rem; }
@container settings (min-width: 46rem) {
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .wide, .savebar { grid-column: 1 / -1; }
  /* Sicherheit: password on the left, deleting apart on the right */
  .card.sec { grid-template-columns: minmax(0, 1fr) auto; }
  .sec h2 { grid-column: 1 / -1; }
  .card.sec .del { align-self: start; margin: 0; }
}
.card { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: 1rem; padding: 1.2rem clamp(.9rem, 4vw, 1.4rem) 1.4rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
.card h2 { font-size: var(--fs-h3); font-weight: 600; color: var(--head); }
.kept { display: grid; gap: .4rem; padding-top: .8rem; border-top: var(--hair); }
.kept-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .6rem; }
.kept-edit, .kept-add { display: grid; gap: .8rem; }
.kept-list { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: .25rem 1rem; margin: 0; }
.kept-list dt { color: var(--ink-3); }
.kept-list dd { margin: 0; overflow-wrap: anywhere; }
.card-h { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .2rem 1rem; }
.fields { display: flex; flex-wrap: wrap; gap: 1rem; }
.fields .field { flex: 1 1 100%; min-width: 0; }
.fields .plz { flex: 1 1 6rem; }
.fields .ort { flex: 3 1 10rem; }
.row { display: flex; flex-wrap: wrap; align-items: start; gap: 1rem 1.75rem; }
.row > .field { flex: 1 1 13rem; }
.row > fieldset { flex: 2 1 17rem; }
.row.view { align-items: end; }
.row.view > * { flex: 0 1 auto; }

/* Live ✓ inside the field */
.in { position: relative; }
.in .good { position: absolute; right: 1rem; top: 50%; translate: 0 -50%; pointer-events: none; }
.in:has(.good) .input { padding-right: 2.75rem; }
.good { display: flex; gap: .4em; align-items: center; color: var(--ready-ink); font-weight: 600; }

/* SVNR: the 4 digits as code boxes, then the birth date. One real input sits on top of the boxes. */
.svnr { display: grid; gap: .5rem; }
.sv-row { display: flex; flex-wrap: wrap; align-items: end; gap: .75rem 1rem; }
.sub-l { font-size: var(--fs-small); color: var(--ink-2); }
.input.date { width: 8rem; }
.input.whole { max-width: 14rem; letter-spacing: .04em; }
.code { position: relative; display: flex; gap: .35rem; width: fit-content; }
.code input { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; padding: 0; border: 0; opacity: 0; font: inherit; caret-color: transparent; cursor: text; }
.cell { display: grid; place-items: center; width: 2.4rem; height: 3rem; border: 1px solid var(--rule-2); border-radius: var(--r-s); background: var(--sheet); font-size: var(--fs-lead); font-weight: 600; transition: border-color .15s; }
.code:hover .cell { border-color: var(--action); }
.code:has(input:focus) .cell.at { border-color: var(--action); outline: 3px solid var(--focus); outline-offset: 2px; }
.code:has(input[aria-invalid="true"]) .cell { border-color: var(--danger); }
[data-contrast="high"] .cell { border-width: 2px; }
.sv-foot { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .25rem 1rem; }
.sv-foot .good { letter-spacing: .03em; }
.sv-foot .linkbtn { font-size: var(--fs-small); min-height: 2rem; }

/* One save for Person, Kontakt and the answer settings; with unsaved changes it stays in view while the page scrolls. */
.savebar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .4rem 1rem; padding: .55rem clamp(.9rem, 4vw, 1.4rem); border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
.savebar.stick { position: sticky; bottom: 0; z-index: 1; }
.done { display: flex; gap: .4em; align-items: center; }
.savebar .btn:disabled { background: var(--sunk); color: var(--ink-3); border-color: var(--rule); cursor: default; transform: none; }
[data-contrast="high"] .savebar .btn:disabled { border-style: dashed; }

select { width: 100%; max-width: 24rem; min-height: 3rem; padding: .4rem 1.1rem; font: inherit; color: var(--ink); background: var(--sheet); border: 1px solid var(--rule-2); border-radius: var(--r-pill); }
select:hover { border-color: var(--action); }
select:focus-visible { border-color: var(--action); outline-offset: 2px; }
[data-contrast="high"] select { border-width: 2px; }
fieldset { min-width: 0; margin: 0; padding: 0; border: 0; }
legend { padding: 0; margin-bottom: .4rem; }
.seg { display: flex; flex-wrap: wrap; gap: .5rem; }
.opt { display: inline-flex; align-items: center; gap: .6rem; min-height: 2.75rem; padding: .4rem 1.1rem .4rem .9rem; border-radius: var(--r-pill); border: 1px solid var(--rule-2); cursor: pointer; font-weight: 600; transition: background-color .15s, border-color .15s; }
.opt:hover { border-color: var(--action); }
.opt:has(input:checked) { border-color: var(--action); background: var(--band); color: var(--head); }
.opt:has(input:focus-visible) { outline: 3px solid var(--focus); outline-offset: 2px; }
.opt input:focus-visible { outline: none; }
[data-contrast="high"] .opt { border-width: 2px; }
.opt input, .toggle input { width: 1.25rem; height: 1.25rem; margin: 0; flex: none; accent-color: var(--action); }
.t-l { font-size: 1.15rem; }
.t-xl { font-size: 1.3rem; }
.toggle { display: flex; align-items: center; gap: .85rem; min-height: 2.75rem; width: fit-content; cursor: pointer; }

.pw { display: grid; gap: 1rem; padding-top: .5rem; }
.pw-rule { display: flex; gap: .4em; align-items: center; }
.pw-rule.ok { color: var(--ready-ink); }
.pw-rule .i { width: 1.05em; height: 1.05em; }
.msg { display: flex; gap: .4em; align-items: flex-start; font-weight: 600; color: var(--danger); }
.msg:empty { display: none; }
.msg.ok { color: var(--ready-ink); }
.msg .i { margin-top: .15em; }
.del { justify-self: start; margin-left: -.8rem; }
</style>
