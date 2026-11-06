<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import type { Plan, StepUpdate } from '../chats'
import { k, t } from '../i18n'
import StepCard from './StepCard.vue'

const props = defineProps<{ plan: Plan; error: string }>()
const emit = defineEmits<{ update: [step: string, body: StepUpdate]; upload: []; wizard: [step: string] }>()

const finished = (status: string) => status === 'done' || status === 'skipped'
const titles = computed(() => Object.fromEntries(props.plan.services.map((s) => [s.id, s.title])))
const doneCount = computed(() => props.plan.steps.filter((s) => finished(s.status)).length)
// "Sie sind hier": the first step that can be done now.
const nowId = computed(() => props.plan.steps.find((s) => s.status === 'available')?.id)
const groups = computed(() =>
  props.plan.services.map((svc) => ({ svc, steps: props.plan.steps.filter((s) => s.service === svc.id) })),
)

// Every card starts closed and shows its one action; details open on demand, so a plan is not a wall of text.
const open = ref(new Set<string>())
function toggle(id: string) {
  if (!open.value.delete(id)) open.value.add(id)
}
// "Mehr dazu" per service: summary, conditions, who decides, letter quotes, source.
const more = ref(new Set<string>())
function toggleMore(id: string) {
  if (!more.value.delete(id)) more.value.add(id)
}

// Overview: one column per service, steps as stations; a click opens the step in the list.
const view = ref<'list' | 'overview'>('list')
const STATE = { done: k('Erledigt'), skipped: k('Übersprungen'), available: k('Offen'), blocked: k('Danach') } as const
function show(id: string) {
  view.value = 'list'
  open.value.add(id)
  nextTick(() => document.getElementById(`t-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}
</script>

<template>
  <section id="plan" class="plan" aria-labelledby="plan-h">
    <div class="plan-h">
      <h2 id="plan-h" tabindex="-1">{{ t('Ihr Plan') }}</h2>
      <p class="plan-n">
        <span class="bar" aria-hidden="true"><span :style="{ width: `${(100 * doneCount) / (plan.steps.length || 1)}%` }"></span></span>{{ t('{done} von {total} erledigt', { done: doneCount, total: plan.steps.length }) }}
      </p>
      <div class="seg-switch" role="group" :aria-label="t('Ansicht')">
        <button type="button" :aria-pressed="view === 'list'" @click="view = 'list'">{{ t('Liste') }}</button>
        <button type="button" :aria-pressed="view === 'overview'" @click="view = 'overview'">{{ t('Übersicht') }}</button>
      </div>
    </div>
    <div v-if="view === 'overview'" class="overview">
      <section v-for="{ svc, steps } in groups" :key="svc.id" class="ov-col" :aria-label="t(svc.title)">
        <h3 class="ov-h">{{ t(svc.title) }}</h3>
        <ol class="ov-steps">
          <li v-for="s in steps" :key="s.id" class="ov-node" :data-status="s.id === nowId ? 'now' : s.status">
            <button type="button" @click="show(s.id)">
              <span class="ov-title">{{ t(s.title) }}</span>
              <span class="ov-state">{{ s.id === nowId ? t('Jetzt dran') : t(STATE[s.status]) }}</span>
            </button>
          </li>
        </ol>
      </section>
    </div>
    <p v-if="error" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ error }}</span></p>

    <section v-for="{ svc, steps } in groups" v-show="view === 'list'" :key="svc.id" class="svc" :aria-labelledby="`svc-${svc.id}`">
      <div class="svc-h">
        <h3 :id="`svc-${svc.id}`">{{ t(svc.title) }}</h3>
        <span class="pill" :data-tone="svc.eligibility === 'likely' ? 'ready' : 'wait'">
          {{ svc.eligibility === 'likely' ? t('Kommt in Frage') : t('Kommt vielleicht in Frage') }}
        </span>
        <span v-if="svc.quotes.length" class="pill" data-tone="wait">{{ t('Laut Ihrem Dokument') }}</span>
        <button type="button" class="linkbtn svc-more-btn" :aria-expanded="more.has(svc.id)" :aria-controls="`more-${svc.id}`" @click="toggleMore(svc.id)">{{ t('Mehr dazu') }}</button>
      </div>
      <div v-if="more.has(svc.id)" :id="`more-${svc.id}`" class="svc-more">
        <p>{{ t(svc.summary) }}</p>
        <blockquote v-for="qt in svc.quotes" :key="qt" class="quote">{{ t('In Ihrem Dokument steht:') }} „{{ qt }}“</blockquote>
        <ul v-if="svc.criteria.length" class="crit">
          <li v-for="c in svc.criteria" :key="c.text" :data-state="c.state">
            <svg class="i" aria-hidden="true"><use :href="c.state === 'met' ? '#i-check' : '#i-info'" /></svg>
            <span>{{ t(c.text) }}<span class="muted"> · {{ c.state === 'met' ? t('erfüllt') : t('noch offen') }}</span></span>
          </li>
        </ul>
        <p v-for="c in svc.checked_by" :key="c">{{ t(c) }}</p>
        <p v-if="svc.responsible">
          {{ t('Zuständig:') }} <b>{{ svc.responsible }}</b>.
          <template v-if="svc.responsible_note">{{ t(svc.responsible_note) }}</template>
          <a v-if="svc.responsible_source" class="src-link" :href="svc.responsible_source" target="_blank" rel="noopener noreferrer">{{ t('Quelle') }}</a>
        </p>
        <p><a class="src-link" :href="svc.source_url" target="_blank" rel="noopener noreferrer">{{ t('Mehr dazu bei der Quelle') }}</a></p>
      </div>
      <ol class="steps">
        <StepCard
          v-for="s in steps"
          :key="s.id"
          :step="s"
          :now="s.id === nowId"
          :open="open.has(s.id)"
          :for-services="(s.services ?? []).map((id) => titles[id] ?? id)"
          @toggle="toggle(s.id)"
          @update="(body) => emit('update', s.id, body)"
          @upload="emit('upload')"
          @wizard="emit('wizard', s.id)"
        />
      </ol>
    </section>

    <div v-if="plan.dropped.length" class="dropped">
      <p class="mini-h">{{ t('Nicht im Plan') }}</p>
      <p v-for="d in plan.dropped" :key="d.id">{{ t(d.title) }}: {{ t(d.reason) }}</p>
    </div>
    <details class="more plan-src">
      <summary>{{ t('„Kommt in Frage“ ist keine Zusage') }}</summary>
      <p>{{ t('Darüber entscheidet die zuständige Stelle. Telefonnummern, Zeiten und Adressen kommen aus dem geprüften Verzeichnis von Zetta, nicht von der KI. Zetta bereitet vor, bucht und sendet aber nichts selbst und stellt keine Diagnosen.') }}</p>
    </details>
  </section>
</template>

<style scoped>
/* "Zum Plan" scrolls here; the margin keeps the heading clear of the sticky plan bar. */
.plan { display: grid; gap: 1.5rem; scroll-margin-top: 3.5rem; }
.plan-h { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; }
.plan-h h2 { font-size: var(--fs-h2); font-weight: 600; color: var(--head); }
.plan-n { display: inline-flex; align-items: center; gap: .65rem; color: var(--ink-3); }
/* Progress in the green accent: the share of finished steps. */
.bar { width: 6rem; height: .55rem; border-radius: var(--r-pill); background: var(--accent-bg); box-shadow: inset 0 0 0 1px var(--accent); overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--accent); }
.seg-switch { display: inline-flex; gap: .25rem; padding: .2rem; border: 1px solid var(--rule-2); border-radius: var(--r-pill); }
.seg-switch button { min-height: 2.5rem; padding: .3rem 1rem; border: 0; border-radius: var(--r-pill); background: none; color: var(--ink-2); font: inherit; font-weight: 600; cursor: pointer; transition: background-color .15s, color .15s; }
.seg-switch button:hover { background: var(--band); }
.seg-switch button[aria-pressed="true"] { background: var(--action); color: var(--on-action); }
.seg-switch button:focus-visible { outline-offset: 1px; }
.overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 1rem; }
.ov-col { display: grid; align-content: start; gap: .6rem; padding: 1rem; border-radius: var(--r-m); background: var(--sunk); }
.ov-h { font-size: 1rem; }
.ov-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: .9rem; }
.ov-node { position: relative; }
/* The line between stations stands for the "after" order inside a service. */
.ov-node + .ov-node::before { content: ""; position: absolute; left: 1.1rem; top: -.9rem; height: .9rem; width: 2px; background: var(--rule-2); }
.ov-node button { display: grid; gap: .15rem; width: 100%; padding: .6rem .9rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); color: var(--ink); font: inherit; text-align: left; cursor: pointer; transition: border-color .15s; }
.ov-node button:hover { border-color: var(--action); }
.ov-title { font-weight: 600; line-height: 1.3; }
.ov-state { font-size: var(--fs-small); color: var(--ink-3); }
.ov-node[data-status="now"] button { border: 2px solid var(--turn-mark); }
.ov-node[data-status="now"] .ov-state { color: var(--turn-ink); font-weight: 700; }
.ov-node[data-status="done"] .ov-state, .ov-node[data-status="skipped"] .ov-state { color: var(--ready-ink); font-weight: 700; }
.ov-node[data-status="blocked"] .ov-title { color: var(--ink-2); }
/* Narrow: the overview would be one long column, so only the list is offered. */
@container (max-width: 40rem) { .seg-switch, .overview { display: none; } .svc { display: grid !important; } }
.svc { display: grid; gap: .6rem; }
.svc-h { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .8rem; }
.svc-h h3 { font-size: var(--fs-h3); }
.svc-more-btn { min-height: 2.75rem; font-weight: 600; }
.quote { margin: 0; padding: .6rem 1rem; border-radius: var(--r-m); background: var(--band); font-weight: 600; }
.svc-more { display: grid; gap: .5rem; max-width: 44rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); color: var(--ink-2); }
.crit { list-style: none; margin: 0; padding: 0; display: grid; gap: .3rem; }
.crit li { display: flex; gap: .5em; align-items: flex-start; }
.crit .i { margin-top: .15em; color: var(--head); }
.crit [data-state="met"] .i { color: var(--ready-mark); }
.steps { list-style: none; margin: .4rem 0 0; padding: 0; display: grid; gap: 1rem; }
.dropped { display: grid; gap: .3rem; color: var(--ink-2); }
.plan-src { font-size: var(--fs-small); color: var(--ink-3); max-width: 44rem; }
.plan-src > summary { color: var(--ink-3); font-weight: 400; }
[data-contrast="high"] :is(.ov-col, .svc-more) { box-shadow: inset 0 0 0 1px var(--ink); }
</style>
