<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { when, type Step, type StepUpdate } from '../chats'

const props = defineProps<{ step: Step; now: boolean; open: boolean; forServices: string[] }>()
const emit = defineEmits<{ toggle: []; update: [body: StepUpdate]; upload: [] }>()

const KIND = {
  call: ['phone', 'Anrufen'],
  email: ['mail', 'E-Mail schreiben'],
  form: ['file', 'Antrag'],
  info: ['info', 'Gut zu wissen'],
  wait: ['clock', 'Abwarten'],
  documents: ['list-check', 'Unterlagen'],
  upload: ['file', 'Hochladen'],
  book: ['ext', 'Online'],
} as const

const s = computed(() => props.step)
const done = computed(() => s.value.status === 'done' || s.value.status === 'skipped')
const state = computed(() => (done.value ? 'done' : props.now ? 'now' : s.value.status === 'blocked' ? 'later' : 'open'))
const stateLabel = computed(
  () => ({ done: 'Erledigt', now: s.value.type === 'wait' ? 'Läuft gerade' : 'Jetzt dran', later: 'Danach', open: 'Offen' })[state.value],
)
const outcomeLabel = computed(() => s.value.outcomes.find((o) => o.id === s.value.outcome)?.label ?? 'Erledigt')
const docs = computed(() => s.value.documents ?? [])
const peek = computed(() => {
  const st = s.value
  if (done.value) return `${outcomeLabel.value}${st.updated_at ? ' · ' + when(st.updated_at) : ''}`
  if (st.type === 'call' && !st.contact && st.institution) return st.institution.name
  if (st.type === 'call' && st.contact) return `${st.contact.value}${st.contact.reachable ? ' · ' + st.contact.reachable.text : ''}`
  if (st.type === 'email' && st.institution) return `An: ${st.institution.name}`
  if (st.type === 'documents') return `${st.checks.length} von ${docs.value.length} bereit`
  if (st.type === 'form' && st.institution) return `Einreichen bei: ${st.institution.name}`
  return st.why
})

// Gaps like "[Ihr Name]" are highlighted, so the user sees what is still missing.
const parts = (text = '') => text.split(/(\[[^\]]+\])/).filter(Boolean).map((t) => ({ t, gap: /^\[.*\]$/.test(t) }))
const hasGap = computed(() => {
  const sc = s.value.script
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
watch(() => s.value.script?.body, (b) => (body.value = b ?? ''), { immediate: true })
const mailto = computed(() => {
  const c = s.value.contact
  if (!c) return ''
  return `mailto:${c.value}?subject=${encodeURIComponent(s.value.script?.subject ?? '')}&body=${encodeURIComponent(body.value)}`
})
const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(`Betreff: ${s.value.script?.subject ?? ''}\n\n${body.value}`)
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
      <div class="card-top">
        <span class="kind"><svg class="i" aria-hidden="true"><use :href="`#i-${KIND[s.type][0]}`" /></svg>{{ KIND[s.type][1] }}</span>
        <span class="state"><svg v-if="state === 'done'" class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ stateLabel }}</span>
      </div>
      <h3 class="card-h">
        <button
          :id="`t-${s.id}`"
          type="button"
          class="card-toggle"
          :aria-expanded="open"
          :aria-controls="`b-${s.id}`"
          @click="emit('toggle')"
        >
          <span class="card-title">{{ s.title }}</span>
          <span class="card-peek">{{ peek }}</span>
          <svg class="i" aria-hidden="true"><use href="#i-chev" /></svg>
        </button>
      </h3>

      <div v-show="open" :id="`b-${s.id}`" class="card-body">
        <!-- Done: the result, and a way back. -->
        <template v-if="done">
          <div class="result">
            <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>
            <div>
              <p><b>{{ outcomeLabel }}</b><template v-if="s.updated_at"> · {{ when(s.updated_at) }}</template></p>
              <p v-if="s.note">{{ s.note }}</p>
            </div>
          </div>
          <p v-if="s.contact" class="contact">
            <svg class="i" aria-hidden="true"><use :href="s.type === 'call' ? '#i-phone' : '#i-mail'" /></svg>
            <a :href="s.contact.href">{{ s.contact.value }}</a><span v-if="s.institution">· {{ s.institution.name }}</span>
          </p>
          <p><button type="button" class="linkbtn" @click="emit('update', { status: 'open' })">Doch noch nicht erledigt</button></p>
        </template>

        <template v-else>
          <p class="why"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span><b>Warum?</b> {{ s.why }}</span></p>
          <p v-if="s.status === 'blocked'" class="hint">Dieser Schritt kommt nach den Schritten davor. Sie können ihn trotzdem schon ansehen.</p>
          <p v-if="forServices.length > 1" class="hint">Gilt für: {{ forServices.join(' und ') }}</p>

          <!-- Call -->
          <template v-if="s.type === 'call'">
            <div v-if="!s.contact" class="callbox">
              <p class="mini-h"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg>{{ s.institution?.name }}</p>
              <p class="hours">Die Nummer kennen Sie selbst: Der Lotse hat keine Daten zu Ihrer Ordination.</p>
            </div>
            <div v-else class="callbox">
              <a class="phone" :href="s.contact.href"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg><span>{{ s.contact.value }}</span><span class="sr"> anrufen</span></a>
              <div class="call-meta">
                <p v-if="s.contact.reachable" class="avail" :data-open="s.contact.reachable.open">{{ s.contact.reachable.text }}</p>
                <p v-else class="hint">Telefonzeiten sind in der Quelle nicht angegeben.</p>
                <p class="hours">{{ s.institution?.name }}<template v-if="s.contact.hours"><br />{{ s.contact.hours }}</template></p>
              </div>
            </div>
            <p v-if="s.outcome === 'not_reached' && s.contact" class="attempt">
              <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg>
              <span>Nicht erreicht<template v-if="s.updated_at"> ({{ when(s.updated_at) }})</template>. Versuchen Sie es noch einmal<template v-if="s.contact.reachable && !s.contact.reachable.open">: {{ s.contact.reachable.text }}</template>.</span>
            </p>
            <div v-if="s.script" class="script">
              <div class="script-h">
                <p class="mini-h"><svg class="i" aria-hidden="true"><use href="#i-chat" /></svg>Ihr Gesprächsleitfaden</p>
                <p class="muted">schon mit Ihren Daten ausgefüllt</p>
              </div>
              <ol class="script-steps">
                <li><span class="lab">Sagen Sie</span><p class="say">„<template v-for="(p, i) in parts(s.script.opening)" :key="i"><mark v-if="p.gap" class="gap">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>“</p></li>
                <li v-if="s.script.have_ready.length">
                  <span class="lab">Halten Sie bereit</span>
                  <dl class="kv">
                    <div v-for="h in s.script.have_ready" :key="h.label"><dt>{{ h.label }}</dt><dd>{{ h.value ?? 'bitte bereithalten' }}</dd></div>
                  </dl>
                </li>
                <li>
                  <span class="lab">Fragen Sie nach – zum Abhaken</span>
                  <ul class="checks">
                    <li v-for="p in s.script.points" :key="p.covers">
                      <label class="check">
                        <input type="checkbox" :checked="s.checks.includes(p.covers)" @change="tick(p.covers, ($event.target as HTMLInputElement).checked)" />
                        <span><template v-for="(q, i) in parts(p.text)" :key="i"><mark v-if="q.gap" class="gap">{{ q.t }}</mark><template v-else>{{ q.t }}</template></template></span>
                      </label>
                    </li>
                  </ul>
                </li>
                <li><span class="lab">Zum Schluss</span><p class="say">„<template v-for="(p, i) in parts(s.script.closing)" :key="i"><mark v-if="p.gap" class="gap">{{ p.t }}</mark><template v-else>{{ p.t }}</template></template>“</p></li>
              </ol>
              <p v-if="hasGap" class="hint">Markierte Stellen fehlen noch. <a href="#einstellungen">In den Einstellungen ergänzen</a></p>
            </div>
            <div v-if="s.contact" class="actions"><a class="btn btn-primary" :href="s.contact.href"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg>Jetzt anrufen</a></div>
            <div class="outcome">
              <button type="button" class="btn btn-secondary" :aria-expanded="outcomeOpen" :aria-controls="`of-${s.id}`" @click="outcomeOpen = !outcomeOpen">
                <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>Anruf erledigt
              </button>
              <form v-if="outcomeOpen" :id="`of-${s.id}`" class="outcome-form" @submit.prevent="saveOutcome">
                <fieldset>
                  <legend class="field-l">Wie ist das Gespräch gelaufen?</legend>
                  <div class="seg">
                    <label v-for="o in s.outcomes" :key="o.id" class="opt"><input v-model="picked" type="radio" :name="`r-${s.id}`" :value="o.id" /><span>{{ o.label }}</span></label>
                  </div>
                </fieldset>
                <div class="field">
                  <label class="field-l" :for="`on-${s.id}`">Was wurde gesagt? <span class="muted">(freiwillig)</span></label>
                  <textarea :id="`on-${s.id}`" v-model="note" class="input" rows="3" maxlength="2000" placeholder="z. B. Antrag kommt per Post"></textarea>
                </div>
                <div class="actions">
                  <button type="submit" class="btn btn-primary">Speichern</button>
                  <button type="button" class="btn btn-quiet" @click="outcomeOpen = false">Abbrechen</button>
                </div>
              </form>
            </div>
          </template>

          <!-- Email -->
          <template v-else-if="s.type === 'email' && s.contact">
            <dl class="mail-meta">
              <dt>An</dt><dd><a :href="s.contact.href">{{ s.contact.value }}</a><span class="muted"> · {{ s.institution?.name }}</span></dd>
              <dt>Betreff</dt><dd>{{ s.script?.subject }}</dd>
              <template v-if="s.form"><dt>Anhang</dt><dd><a :href="s.form.url" target="_blank" rel="noopener noreferrer">{{ s.form.title }}</a> und die Unterlagen aus der Checkliste</dd></template>
            </dl>
            <div class="field">
              <label class="field-l" :for="`m-${s.id}`">Ihre E-Mail <span class="muted">– fertig geschrieben, Sie können sie noch ändern</span></label>
              <textarea :id="`m-${s.id}`" v-model="body" class="input mail" rows="12"></textarea>
              <p v-if="hasGap" class="hint">Stellen in [eckigen Klammern] fehlen noch. <a href="#einstellungen">In den Einstellungen ergänzen</a></p>
            </div>
            <div class="actions">
              <a class="btn btn-primary" :href="mailto"><svg class="i" aria-hidden="true"><use href="#i-mail" /></svg>Im E-Mail-Programm öffnen</a>
              <button type="button" class="btn btn-secondary" @click="copy"><svg class="i" aria-hidden="true"><use href="#i-copy" /></svg>{{ copied ? 'Kopiert' : 'Text kopieren' }}</button>
            </div>
            <p class="sr" aria-live="polite">{{ copied ? 'Text kopiert' : '' }}</p>
          </template>

          <!-- Form -->
          <template v-else-if="s.type === 'form' && s.form">
            <p v-if="s.text">{{ s.text }}</p>
            <div class="actions">
              <a class="btn btn-primary" :href="s.form.url" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ s.form.title }} (PDF)</a>
              <a v-if="s.form.online_url" class="btn btn-secondary" :href="s.form.online_url" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-ext" /></svg>Online stellen</a>
            </div>
            <p v-if="s.institution" class="contact"><svg class="i" aria-hidden="true"><use href="#i-building" /></svg>Einreichen bei: {{ s.institution.name }}<template v-if="s.institution.address">, {{ s.institution.address }}</template></p>
          </template>

          <!-- Checklist -->
          <template v-else-if="s.type === 'documents'">
            <p class="mini-h">Bereit: <span class="muted" aria-live="polite">{{ s.checks.length }} von {{ docs.length }}</span></p>
            <ul class="checks">
              <li v-for="d in docs" :key="d.id">
                <label class="check">
                  <input type="checkbox" :checked="s.checks.includes(d.id)" @change="tick(d.id, ($event.target as HTMLInputElement).checked)" />
                  <span><b>{{ d.title }}</b><small>{{ d.where_to_get }}</small></span>
                </label>
              </li>
            </ul>
          </template>

          <template v-else-if="s.type === 'book' && s.contact">
            <p v-if="s.text">{{ s.text }}</p>
            <div class="actions">
              <a class="btn btn-primary" :href="s.contact.href" target="_blank" rel="noopener noreferrer"><svg class="i" aria-hidden="true"><use href="#i-ext" /></svg>{{ s.contact.label ?? 'Öffnen' }}</a>
            </div>
          </template>

          <template v-else-if="s.type === 'upload'">
            <p v-if="s.text">{{ s.text }}</p>
            <div class="actions"><button type="button" class="btn btn-primary" @click="emit('upload')"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>PDF auswählen</button></div>
          </template>

          <!-- Info, wait, or a call/email without curated contact data -->
          <p v-else-if="s.text">{{ s.text }}</p>

          <div v-if="s.type !== 'call' && s.type !== 'upload'" class="outcome">
            <p v-if="s.outcomes.length > 1" class="field-l">Wie ist es ausgegangen?</p>
            <div class="actions">
              <button v-for="o in s.outcomes" :key="o.id" type="button" class="btn btn-secondary" @click="emit('update', { outcome: o.id })">
                <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>{{ o.label }}
              </button>
            </div>
          </div>
          <a v-if="s.contact?.source_url" class="src-link" :href="s.contact.source_url" target="_blank" rel="noopener noreferrer">Quelle der Kontaktdaten</a>
        </template>
      </div>
    </article>
  </li>
</template>

<style scoped>
/* Plan as a line of stations (from the demo). */
.step { position: relative; padding-left: 2.75rem; }
.step::before { content: ""; position: absolute; left: calc(1rem - 1.5px); top: 2.3rem; bottom: -2.4rem; width: 3px; border-radius: 2px; background: var(--rule-2); }
.step:last-child::before { display: none; }
.step.done::before { background: var(--harbor); }
.st-dot { position: absolute; z-index: 1; left: .45rem; top: 1.15rem; width: 1.1rem; height: 1.1rem; display: grid; place-items: center; border-radius: 50%; border: 3px solid var(--rule-2); background: var(--paper); }
.step.done .st-dot { left: .3rem; top: 1rem; width: 1.4rem; height: 1.4rem; background: var(--harbor); border-color: var(--harbor); color: var(--on-harbor); }
.step.done .st-dot .i { width: .8rem; height: .8rem; stroke-width: 3.5; }
.step.now .st-dot { left: .15rem; top: .85rem; width: 1.7rem; height: 1.7rem; border: 5px solid var(--turn-mark); }
.card { background: var(--sheet); border-radius: var(--r-l); box-shadow: var(--lift); }
.step.later .card, .step.done .card { box-shadow: 0 0 0 1px var(--rule); }
.step.later .card-title { color: var(--ink-2); }
.card-top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .3rem 1rem; padding: 1rem 1.25rem 0; }
.kind { display: inline-flex; align-items: center; gap: .45em; font-weight: 700; font-size: .9rem; color: var(--harbor); }
.state { display: inline-flex; align-items: center; gap: .35em; font-size: .9rem; font-weight: 700; color: var(--ink-3); }
.step.now .state { padding: .15rem .65rem; border-radius: 999px; background: var(--turn-bg); color: var(--turn-ink); }
.step.done .state { color: var(--ready-ink); }
.card-h { margin: 0; font-size: inherit; }
.card-toggle { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: .15rem 1rem; width: 100%; padding: .3rem 1.25rem 1rem; border: 0; border-radius: 0 0 var(--r-l) var(--r-l); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.card-toggle[aria-expanded="true"] { padding-bottom: .75rem; }
.card-title { font-size: 1.2rem; font-weight: 700; line-height: 1.25; hyphens: auto; }
.card-toggle:hover .card-title { color: var(--harbor); }
.card-peek { grid-column: 1; font-size: .95rem; font-weight: 400; color: var(--ink-2); overflow-wrap: anywhere; }
.card-toggle[aria-expanded="true"] .card-peek { display: none; }
.card-toggle > .i { grid-column: 2; grid-row: 1 / span 2; color: var(--ink-3); transition: transform .2s cubic-bezier(.23, 1, .32, 1); }
.card-toggle[aria-expanded="true"] > .i { transform: rotate(180deg); }
.card-body { display: grid; gap: 1.1rem; padding: 0 1.25rem 1.25rem; hyphens: auto; }

.callbox { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1.5rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.phone { display: inline-flex; align-items: center; gap: .55rem; font-size: 1.6rem; font-weight: 700; color: var(--ink); text-decoration: none; font-variant-numeric: tabular-nums; }
.phone:hover { color: var(--harbor); }
.phone .i { color: var(--harbor); }
.call-meta { display: grid; gap: .15rem; }
.hours { font-size: .95rem; color: var(--ink-3); }
.attempt { display: flex; gap: .5em; align-items: flex-start; padding: .7rem .9rem; border-radius: var(--r-m); background: var(--turn-bg); color: var(--turn-ink); font-weight: 600; }
.attempt .i { margin-top: .15em; }
.script { display: grid; gap: .8rem; }
.script-h { display: flex; flex-wrap: wrap; align-items: baseline; gap: .1rem .75rem; }
.script-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 1rem; counter-reset: sc; }
.script-steps > li { counter-increment: sc; display: grid; grid-template-columns: 1.9rem minmax(0, 1fr); column-gap: .8rem; row-gap: .25rem; }
.script-steps > li::before { content: counter(sc); grid-column: 1; grid-row: 1 / span 2; width: 1.9rem; height: 1.9rem; display: grid; place-items: center; border-radius: 50%; background: var(--harbor-tint); color: var(--harbor); font-weight: 700; font-size: .9rem; }
.script-steps > li > * { grid-column: 2; }
.lab { font-size: .85rem; font-weight: 700; color: var(--ink-3); }
.say { font-size: 1.1rem; line-height: 1.5; }
.gap { padding: 0 .2em; border-radius: 4px; background: var(--turn-bg); color: var(--turn-ink); }
.kv { margin: 0; display: grid; gap: .25rem; }
.kv div { display: flex; flex-wrap: wrap; column-gap: 1rem; }
.kv dt { flex: 0 1 13rem; min-width: 0; color: var(--ink-3); }
.kv dd { min-width: 0; margin: 0; font-weight: 700; font-variant-numeric: tabular-nums; }
.outcome { display: grid; gap: .9rem; justify-items: start; padding-top: 1rem; border-top: 1px solid var(--rule); }
.outcome-form { width: 100%; display: grid; gap: 1rem; padding: 1rem; border-radius: var(--r-m); background: var(--sunk); }
.outcome-form fieldset { margin: 0; padding: 0; border: 0; display: grid; gap: .5rem; }
.outcome-form textarea { background: var(--sheet); }
.seg { display: flex; flex-wrap: wrap; gap: .5rem; }
.opt { display: inline-flex; align-items: center; gap: .5rem; min-height: 2.75rem; padding: .4rem .9rem; border-radius: var(--r-s); background: var(--sheet); box-shadow: inset 0 0 0 1px var(--rule-2); cursor: pointer; }
.opt:has(input:checked) { box-shadow: inset 0 0 0 2px var(--harbor); color: var(--harbor); font-weight: 600; }
.opt input { accent-color: var(--harbor); }
.result { display: flex; gap: .65rem; align-items: flex-start; padding: .85rem 1rem; border-radius: var(--r-m); background: var(--ready-bg); color: var(--ready-ink); }
.result .i { margin-top: .15em; }
.result p + p { margin-top: .2rem; color: var(--ink); }
.contact { display: flex; flex-wrap: wrap; gap: .5em; align-items: center; color: var(--ink-2); }
.contact a { color: var(--harbor); }
.mail-meta { margin: 0; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: .3rem 1rem; padding: .85rem 1rem; border-radius: var(--r-m); background: var(--sunk); }
.mail-meta dt { color: var(--ink-3); }
.mail-meta dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.mail-meta a { color: var(--harbor); }
textarea.mail { min-height: 14rem; max-height: 32rem; field-sizing: content; background: var(--sheet); line-height: 1.6; }
[data-contrast="high"] .callbox, [data-contrast="high"] .mail-meta { box-shadow: inset 0 0 0 1px var(--ink); }
@media (forced-colors: active) { .card { border: 1px solid CanvasText; } }
</style>
