<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { Plan, StepUpdate } from '../chats'
import StepCard from './StepCard.vue'

const props = defineProps<{ plan: Plan; error: string }>()
const emit = defineEmits<{ update: [step: string, body: StepUpdate]; upload: [] }>()

const finished = (status: string) => status === 'done' || status === 'skipped'
const titles = computed(() => Object.fromEntries(props.plan.services.map((s) => [s.id, s.title])))
const doneCount = computed(() => props.plan.steps.filter((s) => finished(s.status)).length)
// "Sie sind hier": the first step that can be done now.
const nowId = computed(() => props.plan.steps.find((s) => s.status === 'available')?.id)
const groups = computed(() =>
  props.plan.services.map((svc) => ({ svc, steps: props.plan.steps.filter((s) => s.service === svc.id) })),
)

// Only the current step starts open, so a long plan is not a wall of cards.
const open = ref(new Set<string>())
watch(nowId, (id) => id && open.value.add(id), { immediate: true })
function toggle(id: string) {
  if (!open.value.delete(id)) open.value.add(id)
}

// Overview: one column per service, steps as stations; a click opens the step in the list.
const view = ref<'list' | 'overview'>('list')
const STATE = { done: 'Erledigt', skipped: 'Übersprungen', available: 'Offen', blocked: 'Danach' } as const
function show(id: string) {
  view.value = 'list'
  open.value.add(id)
  nextTick(() => document.getElementById(`t-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
}
</script>

<template>
  <section id="plan" class="plan" aria-labelledby="plan-h">
    <div class="plan-h">
      <h2 id="plan-h" tabindex="-1">Ihr Plan</h2>
      <p class="plan-n">{{ doneCount }} von {{ plan.steps.length }} Schritten erledigt</p>
      <div class="seg-switch" role="group" aria-label="Ansicht">
        <button type="button" :aria-pressed="view === 'list'" @click="view = 'list'">Liste</button>
        <button type="button" :aria-pressed="view === 'overview'" @click="view = 'overview'">Übersicht</button>
      </div>
    </div>
    <div v-if="view === 'overview'" class="overview">
      <section v-for="{ svc, steps } in groups" :key="svc.id" class="ov-col" :aria-label="svc.title">
        <h3 class="ov-h">{{ svc.title }}</h3>
        <ol class="ov-steps">
          <li v-for="s in steps" :key="s.id" class="ov-node" :data-status="s.id === nowId ? 'now' : s.status">
            <button type="button" @click="show(s.id)">
              <span class="ov-title">{{ s.title }}</span>
              <span class="ov-state">{{ s.id === nowId ? 'Jetzt dran' : STATE[s.status] }}</span>
            </button>
          </li>
        </ol>
      </section>
    </div>
    <p v-if="error" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ error }}</span></p>

    <section v-for="{ svc, steps } in groups" v-show="view === 'list'" :key="svc.id" class="svc" :aria-labelledby="`svc-${svc.id}`">
      <div class="svc-h">
        <h3 :id="`svc-${svc.id}`">{{ svc.title }}</h3>
        <span class="pill" :data-tone="svc.eligibility === 'likely' ? 'ready' : 'wait'">
          {{ svc.eligibility === 'likely' ? 'Kommt in Frage' : 'Kommt vielleicht in Frage' }}
        </span>
      </div>
      <p class="svc-sum">{{ svc.summary }}</p>
      <blockquote v-for="qt in svc.quotes" :key="qt" class="quote">In Ihrem Brief steht: „{{ qt }}“</blockquote>
      <details class="svc-more">
        <summary>Voraussetzungen und Zuständigkeit</summary>
        <ul v-if="svc.criteria.length" class="crit">
          <li v-for="c in svc.criteria" :key="c.text" :data-state="c.state">
            <svg class="i" aria-hidden="true"><use :href="c.state === 'met' ? '#i-check' : '#i-info'" /></svg>
            <span>{{ c.text }}<span class="muted"> · {{ c.state === 'met' ? 'erfüllt' : 'noch offen' }}</span></span>
          </li>
        </ul>
        <p v-for="c in svc.checked_by" :key="c">{{ c }}</p>
        <p v-if="svc.responsible">
          Zuständig: <b>{{ svc.responsible }}</b>.
          <template v-if="svc.responsible_note">{{ svc.responsible_note }}</template>
          <a v-if="svc.responsible_source" class="src-link" :href="svc.responsible_source" target="_blank" rel="noopener noreferrer">Quelle</a>
        </p>
        <p><a class="src-link" :href="svc.source_url" target="_blank" rel="noopener noreferrer">Mehr dazu bei der Quelle</a></p>
      </details>
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
        />
      </ol>
    </section>

    <div v-if="plan.dropped.length" class="dropped">
      <p class="mini-h">Nicht im Plan</p>
      <p v-for="d in plan.dropped" :key="d.id">{{ d.title }}: {{ d.reason }}</p>
    </div>
    <p class="plan-src">
      <svg class="i" aria-hidden="true"><use href="#i-info" /></svg>
      <span>„Kommt in Frage“ ist keine Zusage: Darüber entscheidet die zuständige Stelle. Telefonnummern, Zeiten und Adressen kommen aus dem geprüften Verzeichnis des Lotsen, nicht von der KI. Der Lotse bereitet vor, er bucht und sendet nichts selbst und stellt keine Diagnosen.</span>
    </p>
  </section>
</template>

<style scoped>
.plan { display: grid; gap: 1.5rem; }
.plan-h { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; }
.plan-h h2 { font-size: 1.5rem; }
.plan-n { color: var(--ink-3); font-variant-numeric: tabular-nums; }
.seg-switch { display: inline-flex; padding: .2rem; border-radius: 999px; background: var(--sunk); }
.seg-switch button { min-height: 2.5rem; padding: .3rem .9rem; border: 0; border-radius: 999px; background: none; color: var(--ink-2); font: inherit; font-weight: 600; cursor: pointer; }
.seg-switch button[aria-pressed="true"] { background: var(--sheet); color: var(--harbor); box-shadow: var(--lift); }
.overview { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); gap: 1rem; }
.ov-col { display: grid; align-content: start; gap: .6rem; padding: .9rem; border-radius: var(--r-l); background: var(--sunk); }
.ov-h { font-size: 1rem; }
.ov-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: .9rem; }
.ov-node { position: relative; }
/* The line between stations stands for the "after" order inside a service. */
.ov-node + .ov-node::before { content: ""; position: absolute; left: 1.1rem; top: -.9rem; height: .9rem; width: 2px; background: var(--rule-2); }
.ov-node button { display: grid; gap: .15rem; width: 100%; padding: .6rem .8rem; border: 0; border-radius: var(--r-m); background: var(--sheet); color: var(--ink); font: inherit; text-align: left; cursor: pointer; box-shadow: 0 0 0 1px var(--rule); }
.ov-node button:hover { box-shadow: 0 0 0 2px var(--harbor); }
.ov-title { font-weight: 700; line-height: 1.3; }
.ov-state { font-size: .85rem; color: var(--ink-3); }
.ov-node[data-status="now"] button { box-shadow: 0 0 0 3px var(--turn-mark); }
.ov-node[data-status="now"] .ov-state { color: var(--turn-ink); font-weight: 700; }
.ov-node[data-status="done"] .ov-state, .ov-node[data-status="skipped"] .ov-state { color: var(--ready-ink); font-weight: 700; }
.ov-node[data-status="blocked"] .ov-title { color: var(--ink-2); font-weight: 600; }
/* Narrow: the overview would be one long column, so only the list is offered. */
@container (max-width: 40rem) { .seg-switch, .overview { display: none; } .svc { display: grid !important; } }
.svc { display: grid; gap: .6rem; }
.svc-h { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .8rem; }
.svc-h h3 { font-size: 1.25rem; }
.svc-sum { color: var(--ink-2); max-width: 44rem; }
.quote { max-width: 44rem; margin: 0; padding: .55rem .9rem; border-left: 3px solid var(--harbor); border-radius: 0 var(--r-s) var(--r-s) 0; background: var(--sunk); font-weight: 600; }
.svc-more { max-width: 44rem; color: var(--ink-2); }
.svc-more summary { width: fit-content; min-height: 2.75rem; display: flex; align-items: center; color: var(--harbor); font-weight: 600; cursor: pointer; }
.svc-more > :not(summary) { margin-top: .5rem; }
.crit { list-style: none; margin: 0; padding: 0; display: grid; gap: .3rem; }
.crit li { display: flex; gap: .5em; align-items: flex-start; }
.crit .i { margin-top: .15em; color: var(--harbor); }
.steps { list-style: none; margin: .4rem 0 0; padding: 0; display: grid; gap: 1rem; }
.dropped { display: grid; gap: .3rem; color: var(--ink-2); }
.plan-src { display: flex; gap: .5em; font-size: .9rem; color: var(--ink-3); max-width: 44rem; }
.plan-src .i { margin-top: .15em; }
</style>
