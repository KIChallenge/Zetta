<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
</script>

<template>
  <section id="plan" class="plan" aria-labelledby="plan-h">
    <div class="plan-h">
      <h2 id="plan-h" tabindex="-1">Ihr Plan</h2>
      <p class="plan-n">{{ doneCount }} von {{ plan.steps.length }} Schritten erledigt</p>
    </div>
    <p v-if="error" class="err" role="alert"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ error }}</span></p>

    <section v-for="{ svc, steps } in groups" :key="svc.id" class="svc" :aria-labelledby="`svc-${svc.id}`">
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
