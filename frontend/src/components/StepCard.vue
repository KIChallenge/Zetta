<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { when, type Step, type StepUpdate } from '../chats'
import { hours, k, locale, t, translating } from '../i18n'

const props = defineProps<{ step: Step; now: boolean; open: boolean; forServices: string[] }>()
const emit = defineEmits<{ toggle: []; update: [body: StepUpdate]; upload: []; wizard: [] }>()

const KIND = {
  call: ['phone', k('Anrufen')],
  email: ['mail', k('E-Mail schreiben')],
  form: ['file', k('Antrag')],
  info: ['info', k('Gut zu wissen')],
  wait: ['clock', k('Abwarten')],
  documents: ['list-check', k('Unterlagen')],
  upload: ['file', k('Hochladen')],
  book: ['ext', k('Online')],
} as const

const s = computed(() => props.step)
const done = computed(() => s.value.status === 'done' || s.value.status === 'skipped')
const state = computed(() => (done.value ? 'done' : props.now ? 'now' : s.value.status === 'blocked' ? 'later' : 'open'))
const stateLabel = computed(
  () => t(({ done: k('Erledigt'), now: s.value.type === 'wait' ? k('Läuft gerade') : k('Jetzt dran'), later: k('Danach'), open: k('Offen') })[state.value]),
)
const outcomeLabel = computed(() => t(s.value.outcomes.find((o) => o.id === s.value.outcome)?.label ?? 'Erledigt'))
const docs = computed(() => s.value.documents ?? [])
const meter = computed(() => {
  const w = s.value.form?.wizard
  return w && w.total ? Math.round((100 * w.done) / w.total) : 100
})

// Collapsed, a card shows one line (who, or the result) and the one thing to do now; the rest opens on demand.
const line = computed(() => {
  const st = s.value
  if (done.value) return `${outcomeLabel.value}${st.updated_at ? ' · ' + when(st.updated_at) : ''}`
  if (st.type === 'documents') return t('{done} von {total} bereit', { done: st.checks.length, total: docs.value.length })
  return t(st.institution?.name ?? '')
})
const reach = computed(() => (!done.value && s.value.type === 'call' ? s.value.contact?.reachable : undefined))
// Info and wait steps have nothing to open elsewhere: their outcome is the action.
const outcomeFirst = computed(() => s.value.type === 'info' || s.value.type === 'wait')
const act = computed(() => {
  const st = s.value
  if (st.status !== 'available') return false
  if (st.type === 'call') return !!(st.contact || st.script)
  if (st.type === 'email' || st.type === 'book') return !!st.contact
  if (st.type === 'form') return !!st.form
  return st.type !== 'documents'
})
const notReached = computed(() => !done.value && s.value.outcome === 'not_reached' && !!s.value.contact)

// Gaps like "[Ihr Name]" are highlighted, so the user sees what is still missing.
const parts = (text = '') => text.split(/(\[[^\]]+\])/).filter(Boolean).map((t) => ({ t, gap: /^\[.*\]$/.test(t) }))
// In another language the German line is read out and the translation sits below it. Both come from the corpus,
// so they say the same; an LLM script could differ from its translation.
const plain = computed(() => (translating.value ? s.value.script?.plain : undefined))
function fillSlots(text: string | undefined, translate: boolean) {
  if (!text) return text
  const slots = plain.value!.slots
  return text.replace(/\{([a-z_]+\.[a-z_]+)\}/g, (m, name: string) => {
    const slot = slots[name]
    if (!slot) return m
    if (slot.value) return translate && name === 'subject.relation' ? t(slot.value) : slot.value
    return `[${translate ? t(slot.gap) : slot.gap}]`
  })
}
function scriptOf(translate: boolean) {
  const tpl = plain.value!.template
  const show = (text?: string) => fillSlots(text && translate ? t(text) : text, translate)
  return {
    opening: show(tpl.opening),
    points: tpl.points?.map((p) => ({ covers: p.covers, text: show(p.text)! })),
    closing: show(tpl.closing),
    subject: show(tpl.subject),
    body: show(tpl.body),
  }
}
const script = computed(() => (s.value.script && plain.value ? { ...s.value.script, ...scriptOf(false) } : s.value.script))
const translated = computed(() => (plain.value ? scriptOf(true) : null))
const pointText = (covers: string) => translated.value?.points?.find((p) => p.covers === covers)?.text
const hasGap = computed(() => {
  const sc = script.value
  const texts = [sc?.opening, sc?.closing, sc?.body, sc?.subject, ...(sc?.points ?? []).map((p) => p.text)]
  return texts.some((t) => t && /\[[^\]]+\]/.test(t))
})

function tick(id: string, on: boolean) {
  const checks = on ? [...s.value.checks, id] : s.value.checks.filter((c) => c !== id)
  emit('update', { checks })
}

// Call outcome form
const outcomeOpen = ref(false)
const picked = ref('reached')
const note = ref('')
function saveOutcome() {
  emit('update', { outcome: picked.value, note: note.value })
  outcomeOpen.value = false
}

// Email: editable before sending, so the user's changes go into the mail client or the clipboard.
const body = ref('')
watch(() => script.value?.body, (b) => (body.value = b ?? ''), { immediate: true })
const mailto = computed(() => {
  const c = s.value.contact
  if (!c) return ''
  return `mailto:${c.value}?subject=${encodeURIComponent(script.value?.subject ?? '')}&body=${encodeURIComponent(body.value)}`
})
const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(`Betreff: ${script.value?.subject ?? ''}\n\n${body.value}`)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <li class="step" :class="state">
    <span class="st-dot" aria-hidden="true"><svg v-if="state === 'done'" class="i"><use href="#i-check" /></svg></span>
    <article class="card" :aria-labelledby="`t-${s.id}`">
      <h3 class="card-h">
        <button
          :id="`t-${s.id}`"
          type="button"
          class="card-toggle"
          :aria-expanded="open"
          :aria-controls="`b-${s.id}`"
          @click="emit('toggle')"
        >
          <svg class="i kind" aria-hidden="true"><use :href="`#i-${KIND[s.type][0]}`" /></svg>
          <span class="card-title"><span class="sr">{{ t(KIND[s.type][1]) }}: </span>{{ t(s.title) }}</span>
          <span class="state" :class="{ sr: state === 'open' }"><svg v-if="state === 'done'" class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ stateLabel }}</span>
          <svg class="i chev" aria-hidden="true"><use href="#i-chev" /></svg>
        </button>
      </h3>

      <div v-if="line || reach || notReached || act" class="card-sub">
        <p v-if="line || reach" class="card-line" :aria-live="s.type === 'documents' ? 'polite' : undefined">
          <span v-if="line">{{ line }}</span>
          <span v-if="reach" class="avail" :data-open="reach.open">{{ t(reach.text) }}</span>
        </p>
        <p v-if="notReached" class="attempt">
          <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
          <span>{{ t('Nicht erreicht') }}<template v-if="s.updated_at"> ({{ when(s.updated_at) }})</template>. {{ t('Versuchen Sie es noch einmal.') }}</span>
        </p>
        <ul v-if="act && s.doctors" class="doctors">
          <li v-for="d in s.doctors" :key="d.id" class="doctor">
            <div class="doctor-info">
              <strong>{{ d.name }}</strong>
              <span v-if="d.warning" class="err"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ t(d.warning) }} <a v-if="d.warning_source" :href="d.warning_source" target="_blank" rel="noopener noreferrer">{{ t('Mehr dazu') }}</a></span></span>
              <span v-else class="doctor-contract">{{ t(d.contract) }}</span>
              <span>{{ d.address }}</span>
              <span class="hint">{{ t('Öffnungszeiten:') }} {{ d.contact.hours ? hours(d.contact.hours) : t('in der Quelle nicht angegeben') }}</span>
            </div>
            <a class="btn btn-secondary call" :href="d.contact.href"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg><span class="num">{{ d.contact.value }}</span><span class="sr"> {{ t('anrufen') }}</span></a>
          </li>
        </ul>
        <p v-if="act && s.doctors" class="hint">
          {{ t('Gereiht nach Kassenvertrag, Bezirk und Zeit, keine Empfehlung.') }} {{ t('Quelle:') }} <a :href="s.doctors_source?.url" target="_blank" rel="noopener noreferrer">praxisplan.at</a>, {{ t('Stand') }} {{ s.doctors_source?.scraped_at.split('-').reverse().join('.') }}.
          <a v-if="s.more" :href="s.more.href" target="_blank" rel="noopener noreferrer">{{ t('Weitere Ordinationen suchen') }}</a>
        </p>
        <div v-if="act" class="actions">
          <template v-if="s.type === 'call'">
            <a v-if="s.contact" class="btn btn-primary call" :href="s.contact.href"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg><span class="num">{{ s.contact.value }}</span><span class="sr"> {{ t('anrufen') }}</span></a>
            <button v-if="s.script" type="button" class="btn btn-quiet" :aria-expanded="open" :aria-controls="`b-${s.id}`" @click="emit('toggle')">{{ t('Gesprächsleitfaden') }}</button>
          </template>
          <template v-else-if="s.type === 'email'">
            <a class="btn btn-primary" :href="mailto"><svg class="i" aria-hidden="true"><use href="#i-mail" /></svg>{{ t('E-Mail öffnen') }}</a>
            <button type="button" class="btn btn-quiet" :aria-expanded="open" :aria-controls="`b-${s.id}`" @click="emit('toggle')">{{ t('E-Mail ansehen') }}</button>
          </template>
          <button v-else-if="s.type === 'form' && s.form?.wizard" type="button" class="btn btn-primary" @click="emit('wizard')"><svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg>{{ t('Formular ausfüllen') }}</button>
          <a v-else-if="s.type === 'form' && s.form" class="btn btn-primary" :href="s.form.url" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ s.form.title }} (PDF)</a>
          <a v-else-if="s.type === 'book' && s.contact" class="btn btn-primary" :href="s.contact.href" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-ext" /></svg>{{ t(s.contact.label ?? 'Öffnen') }}</a>
          <button v-else-if="s.type === 'upload'" type="button" class="btn btn-primary" @click="emit('upload')"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ t('PDF auswählen') }}</button>
          <template v-else-if="outcomeFirst">
            <button v-for="o in s.outcomes" :key="o.id" type="button" class="btn btn-secondary" @click="emit('update', { outcome: o.id })">
              <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t(o.label) }}
            </button>
          </template>
        </div>
      </div>

      <div v-show="open" :id="`b-${s.id}`" class="card-body">
        <!-- Done: the result, and a way back. -->
        <template v-if="done">
          <p v-if="s.note">{{ s.note }}</p>
          <p v-if="s.contact" class="contact">
            <svg class="i" aria-hidden="true"><use :href="s.type === 'call' ? '#i-phone' : '#i-mail'" /></svg>
            <a :href="s.contact.href">{{ s.contact.value }}</a><span v-if="s.institution">· {{ t(s.institution.name) }}</span>
          </p>
          <p><button type="button" class="linkbtn" @click="emit('update', { status: 'open' })">{{ t('Doch noch nicht erledigt') }}</button></p>
        </template>

        <template v-else>
          <p class="why"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span>{{ t(s.why) }}</span></p>
          <p v-if="forServices.length > 1" class="hint">{{ t('Gilt für:') }} {{ forServices.map((f) => t(f)).join(', ') }}</p>

          <!-- Call -->
          <template v-if="s.type === 'call'">
            <p v-if="s.phone_note" class="why"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span>{{ t(s.phone_note) }}</span></p>
            <p v-if="s.switchable"><button type="button" class="linkbtn" @click="emit('update', { by_email: true })">{{ t('Lieber eine E-Mail schreiben') }}</button></p>
            <p v-if="!s.contact && !s.doctors" class="hint">{{ t('Die Nummer kennen Sie selbst: Der Lotse hat keine Daten zu Ihrer Ordination.') }}</p>
            <p v-else-if="s.contact" class="hint">{{ t('Telefonzeiten:') }} {{ s.contact.hours ? hours(s.contact.hours) : t('in der Quelle nicht angegeben') }}</p>
            <p v-if="translated" class="hint">{{ t('Sprechen Sie den deutschen Text. Die Übersetzung darunter hilft Ihnen beim Verstehen.') }}</p>
            <div v-if="script" class="script">
              <ol class="script-steps">
                <li><span class="lab caps">{{ t('Sagen Sie') }}</span><p class="say">„<template v-for="(p, i) in parts(script.opening)" :key="i"><mark v-if="p.gap" class="gap">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>“</p><p v-if="translated" class="say-tr" :lang="locale">{{ translated.opening }}</p></li>
                <li v-if="script.have_ready.length">
                  <span class="lab caps">{{ t('Halten Sie bereit') }}</span>
                  <dl class="kv">
                    <div v-for="h in script.have_ready" :key="h.label"><dt>{{ t(h.label) }}</dt><dd>{{ h.value ?? t('bitte bereithalten') }}</dd></div>
                  </dl>
                </li>
                <li>
                  <span class="lab caps">{{ t('Fragen Sie nach') }}</span>
                  <ul class="checks">
                    <li v-for="p in script.points" :key="p.covers">
                      <label class="check">
                        <input type="checkbox" :checked="s.checks.includes(p.covers)" @change="tick(p.covers, ($event.target as HTMLInputElement).checked)" />
                        <span><template v-for="(q, i) in parts(p.text)" :key="i"><mark v-if="q.gap" class="gap">{{ q.t }}</mark><template v-else>{{ q.t }}</template></template><small v-if="pointText(p.covers)" class="say-tr" :lang="locale">{{ pointText(p.covers) }}</small></span>
                      </label>
                    </li>
                  </ul>
                </li>
                <li><span class="lab caps">{{ t('Zum Schluss') }}</span><p class="say">„<template v-for="(p, i) in parts(script.closing)" :key="i"><mark v-if="p.gap" class="gap">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>“</p><p v-if="translated" class="say-tr" :lang="locale">{{ translated.closing }}</p></li>
              </ol>
              <p v-if="hasGap" class="hint">{{ t('Markierte Stellen fehlen noch.') }} <a href="#einstellungen">{{ t('In den Einstellungen ergänzen') }}</a></p>
            </div>
            <div class="outcome">
              <button type="button" class="btn btn-secondary" :aria-expanded="outcomeOpen" :aria-controls="`of-${s.id}`" @click="outcomeOpen = !outcomeOpen">
                <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t('Anruf erledigt') }}
              </button>
              <form v-if="outcomeOpen" :id="`of-${s.id}`" class="outcome-form" @submit.prevent="saveOutcome">
                <fieldset>
                  <legend class="field-l">{{ t('Wie ist das Gespräch gelaufen?') }}</legend>
                  <div class="seg">
                    <label v-for="o in s.outcomes" :key="o.id" class="opt"><input v-model="picked" type="radio" :name="`r-${s.id}`" :value="o.id" /><span>{{ t(o.label) }}</span></label>
                  </div>
                </fieldset>
                <div class="field">
                  <label class="field-l" :for="`on-${s.id}`">{{ t('Was wurde gesagt?') }} <span class="muted">{{ t('(freiwillig)') }}</span></label>
                  <textarea :id="`on-${s.id}`" v-model="note" class="input" rows="3" maxlength="2000" :placeholder="t('z. B. Antrag kommt per Post')"></textarea>
                </div>
                <div class="actions">
                  <button type="submit" class="btn btn-primary">{{ t('Speichern') }}</button>
                  <button type="button" class="btn btn-quiet" @click="outcomeOpen = false">{{ t('Abbrechen') }}</button>
                </div>
              </form>
            </div>
          </template>

          <!-- Email -->
          <template v-else-if="s.type === 'email' && s.contact">
            <p v-if="s.by_email"><button type="button" class="linkbtn" @click="emit('update', { by_email: false })"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg>{{ t('Doch lieber anrufen') }}</button></p>
            <dl class="mail-meta">
              <dt>{{ t('An') }}</dt><dd><a :href="s.contact.href">{{ s.contact.value }}</a></dd>
              <dt>{{ t('Betreff') }}</dt><dd>{{ script?.subject }}<small v-if="translated" class="say-tr" :lang="locale">{{ translated.subject }}</small></dd>
              <template v-if="s.form"><dt>{{ t('Anhang') }}</dt><dd><button v-if="s.form.wizard" type="button" class="linkbtn" @click="emit('wizard')">{{ s.form.title }} ({{ t('ausfüllen') }})</button><a v-else :href="s.form.url" target="_blank" rel="noopener noreferrer">{{ s.form.title }}</a> {{ t('und die Unterlagen aus der Checkliste') }}</dd></template>
            </dl>
            <div class="field">
              <label class="field-l" :for="`m-${s.id}`">{{ t('Ihre E-Mail') }} <span class="muted">{{ t('(änderbar)') }}</span></label>
              <textarea :id="`m-${s.id}`" v-model="body" class="input mail" rows="12"></textarea>
              <p v-if="hasGap" class="hint">{{ t('Stellen in [eckigen Klammern] fehlen noch.') }} <a href="#einstellungen">{{ t('In den Einstellungen ergänzen') }}</a></p>
              <details v-if="translated" class="more"><summary>{{ t('Übersetzung der E-Mail') }}</summary><p class="say-tr mail-tr" :lang="locale">{{ translated.body }}</p></details>
            </div>
            <div class="actions">
              <button type="button" class="btn btn-secondary" @click="copy"><svg class="i" aria-hidden="true"><use href="#i-copy" /></svg>{{ copied ? t('Kopiert') : t('Text kopieren') }}</button>
            </div>
            <p class="sr" aria-live="polite">{{ copied ? t('Text kopiert') : '' }}</p>
          </template>

          <!-- Form -->
          <template v-else-if="s.type === 'form' && s.form">
            <p v-if="s.text">{{ t(s.text) }}</p>
            <div v-if="s.form.wizard" class="wz-meter">
              <p><b>{{ t('{done} von {total} Pflichtangaben', { done: s.form.wizard.done, total: s.form.wizard.total }) }}</b> · {{ s.form.title }}</p>
              <div class="bar" role="progressbar" :aria-valuenow="meter" aria-valuemin="0" aria-valuemax="100" :aria-label="t('Schon ausgefüllt')"><span :style="{ width: `${meter}%` }" /></div>
              <p class="hint">{{ t('Vorausgefüllt aus Ihrem Profil, den gemerkten Angaben und dem Gespräch. Den Rest fragt der Lotse Schritt für Schritt.') }}</p>
              <!-- Above, the card shows this button once the step is due; it can be filled in before. -->
              <div v-if="!act" class="actions"><button type="button" class="btn btn-primary" @click="emit('wizard')"><svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg>{{ t('Formular ausfüllen') }}</button></div>
            </div>
            <p v-if="s.form.wizard" class="hint">
              {{ t('Bitte prüfen, den Rest ergänzen und unterschreiben.') }} <a :href="s.form.url" target="_blank" rel="noopener noreferrer">{{ t('Leeres Formular') }}</a>
            </p>
            <div v-if="s.form.online_url" class="actions">
              <a class="btn btn-secondary" :href="s.form.online_url" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-ext" /></svg>{{ t('Online stellen') }}</a>
            </div>
            <p v-if="s.institution" class="contact"><svg class="i" aria-hidden="true"><use href="#i-building" /></svg><span>{{ t('Einreichen bei:') }} {{ t(s.institution.name) }}<template v-if="s.institution.address">, {{ s.institution.address }}</template></span></p>
          </template>

          <!-- Checklist -->
          <ul v-else-if="s.type === 'documents'" class="checks">
            <li v-for="d in docs" :key="d.id">
              <label class="check">
                <input type="checkbox" :checked="s.checks.includes(d.id)" @change="tick(d.id, ($event.target as HTMLInputElement).checked)" />
                <span><b>{{ t(d.title) }}</b><small>{{ t(d.where_to_get) }}</small></span>
              </label>
            </li>
          </ul>

          <!-- Book, upload, info, wait, or a call/email without curated contact data -->
          <p v-else-if="s.text">{{ t(s.text) }}</p>

          <div v-if="s.type !== 'call' && s.type !== 'upload' && !(outcomeFirst && act)" class="outcome">
            <p v-if="s.outcomes.length > 1" class="field-l">{{ t('Wie ist es ausgegangen?') }}</p>
            <div class="actions">
              <button v-for="o in s.outcomes" :key="o.id" type="button" class="btn btn-secondary" @click="emit('update', { outcome: o.id })">
                <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ t(o.label) }}
              </button>
            </div>
          </div>
          <a v-if="s.contact?.source_url" class="src-link" :href="s.contact.source_url" target="_blank" rel="noopener noreferrer">{{ t('Quelle') }}</a>
        </template>
      </div>
    </article>
  </li>
</template>

<style scoped>
/* The plan reads as a wayfinding line: stations on a rail, the current one marked "you are here". */
.step { position: relative; padding-left: 2.75rem; }
.step::before { content: ""; position: absolute; left: calc(1rem - 1px); top: 2.2rem; bottom: -2.2rem; width: 2px; background: var(--rule-2); }
.step:last-child::before { display: none; }
.step.done::before { background: var(--ready-mark); }
.st-dot { position: absolute; z-index: 1; left: .5rem; top: 1.15rem; width: 1rem; height: 1rem; display: grid; place-items: center; border-radius: 50%; border: 2px solid var(--rule-2); background: var(--paper); }
.step.done .st-dot { left: .3rem; top: .95rem; width: 1.4rem; height: 1.4rem; background: var(--ready-mark); border-color: var(--ready-mark); color: var(--paper); }
.step.done .st-dot .i { width: .8rem; height: .8rem; stroke-width: 3.5; }
.step.now .st-dot { left: .2rem; top: .85rem; width: 1.6rem; height: 1.6rem; border: 3px solid var(--turn-mark); background: var(--turn-mark); box-shadow: inset 0 0 0 4px var(--paper); }
.card { --in: calc(1.25rem + 1.2em + .75rem); background: var(--sheet); border: var(--hair); border-radius: var(--r-m); }
.step.now .card { border: 2px solid var(--turn-mark); }
[data-contrast="high"] .step.now .card { border-width: 3px; }
.card-h { margin: 0; font-size: inherit; }
.card-toggle { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: .75rem; width: 100%; padding: 1rem 1.25rem; border: 0; border-radius: var(--r-m); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.card-toggle:focus-visible { outline-offset: -3px; }
.kind { color: var(--head); }
.card-title { font-size: var(--fs-h3); font-weight: 600; line-height: 1.25; color: var(--head); hyphens: auto; }
.card-toggle:hover .card-title { text-decoration: underline; text-underline-offset: .15em; text-decoration-thickness: 1px; }
.step.later .card-title, .step.done .card-title { color: var(--ink-2); }
.state { display: inline-flex; align-items: center; gap: .35em; font-size: var(--fs-small); font-weight: 700; color: var(--ink-3); }
.step.now .state { padding: .1rem .7rem; border-radius: var(--r-pill); background: var(--todo-bg); color: var(--todo-ink); }
.step.done .state { color: var(--ready-ink); }
.chev { color: var(--ink-3); transition: transform .2s cubic-bezier(.23, 1, .32, 1); }
.card-toggle[aria-expanded="true"] .chev { transform: rotate(180deg); }
/* Narrow: the state goes under the title, so the title keeps the width. */
@container (max-width: 34rem) {
  .card { --in: calc(1rem + 1.2em + .5rem); }
  .card-toggle { grid-template-columns: auto minmax(0, 1fr) auto; gap: .3rem .5rem; padding-inline: 1rem; }
  .card-sub { padding-right: 1rem; }
  .card-toggle .state { grid-column: 2; grid-row: 2; justify-self: start; }
  .card-toggle .chev { grid-column: 3; grid-row: 1; }
}
.card-sub { display: grid; gap: .75rem; margin-top: -.5rem; padding: 0 1.25rem 1.1rem var(--in); }
.card-line { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem 1rem; color: var(--ink-2); overflow-wrap: anywhere; }
.btn.call { font-size: var(--fs-lead); }
.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.card-body { display: grid; gap: 1.1rem; padding: 1.1rem 1.25rem 1.25rem; border-top: var(--hair); hyphens: auto; }

.attempt { display: flex; gap: .5em; align-items: flex-start; padding: .6rem 1rem; border-radius: var(--r-m); background: var(--turn-bg); color: var(--turn-ink); font-weight: 600; }
.attempt .i { margin-top: .15em; }
.script { display: grid; gap: .8rem; }
/* A real sequence (what to say, in order), so the steps are numbered. */
.script-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 1.1rem; counter-reset: sc; }
.script-steps > li { counter-increment: sc; display: grid; grid-template-columns: 1.75rem minmax(0, 1fr); column-gap: .85rem; row-gap: .3rem; }
.script-steps > li::before { content: counter(sc); grid-column: 1; grid-row: 1 / span 2; width: 1.75rem; height: 1.75rem; display: grid; place-items: center; border-radius: 50%; border: 1.5px solid var(--accent); color: var(--accent); font-weight: 700; font-size: var(--fs-small); }
.script-steps > li > * { grid-column: 2; }
.lab { align-self: center; }
.say { font-size: var(--fs-lead); line-height: 1.5; }
/* Still to fill in: tinted and underlined, so it does not read as "done". */
.gap { padding: 0 .2em; border-radius: 4px; background: var(--turn-bg); color: var(--turn-ink); box-shadow: inset 0 -2px 0 var(--turn-mark); }
.kv { margin: 0; display: grid; gap: .25rem; }
.kv div { display: flex; flex-wrap: wrap; column-gap: 1rem; }
.kv dt { flex: 0 1 13rem; min-width: 0; color: var(--ink-3); }
.kv dd { min-width: 0; margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.outcome { display: grid; gap: .9rem; justify-items: start; padding-top: 1.1rem; border-top: var(--hair); }
.wz-meter { display: grid; gap: .4rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.wz-meter .bar { height: .55rem; border-radius: var(--r-pill); background: var(--accent-bg); box-shadow: inset 0 0 0 1px var(--accent); overflow: hidden; }
.wz-meter .bar span { display: block; height: 100%; background: var(--accent); }
.outcome-form { width: 100%; display: grid; gap: 1rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.outcome-form fieldset { margin: 0; padding: 0; border: 0; display: grid; gap: .5rem; }
.seg { display: flex; flex-wrap: wrap; gap: .5rem; }
.opt { display: inline-flex; align-items: center; gap: .5rem; min-height: 2.75rem; padding: .4rem 1.1rem .4rem .9rem; border: 1px solid var(--rule-2); border-radius: var(--r-pill); background: var(--sheet); cursor: pointer; }
.opt:hover { border-color: var(--action); }
.opt:has(input:checked) { border-color: var(--action); background: var(--band); color: var(--head); font-weight: 600; }
.opt:has(input:focus-visible) { outline: 3px solid var(--focus); outline-offset: 2px; }
.opt input { accent-color: var(--action); }
.say-tr { display: block; margin-top: .2rem; font-size: var(--fs-small); color: var(--ink-3); }
.mail-tr { white-space: pre-line; }
.doctors { display: grid; gap: .75rem; margin: 0; padding: 0; list-style: none; }
.doctor { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: center; justify-content: space-between; padding-bottom: .75rem; border-bottom: 1px solid var(--rule-2); }
.doctor-info { display: grid; gap: .1rem; min-width: 0; flex: 1 1 14rem; }
.doctor-contract { font-size: var(--fs-small); font-weight: 600; color: var(--ink-2); }
.contact { display: flex; gap: .5em; align-items: flex-start; color: var(--ink-2); }
.contact .i { margin-top: .15em; color: var(--head); }
.mail-meta { margin: 0; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .3rem 1rem; padding: .85rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.mail-meta dt { color: var(--ink-3); }
.mail-meta dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
textarea.mail { min-height: 14rem; max-height: 32rem; field-sizing: content; line-height: 1.6; }
[data-contrast="high"] .mail-meta, [data-contrast="high"] .outcome-form { box-shadow: inset 0 0 0 1px var(--ink); }
</style>
