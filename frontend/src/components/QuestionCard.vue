<script setup lang="ts">
import { ref } from 'vue'
import type { Chip } from '../chats'

// One question at a time. Only the latest one has chips; answered ones stay as plain text in the history.
defineProps<{ text: string; why: string; chips: Chip[]; active: boolean; multi?: boolean }>()
const emit = defineEmits<{ answer: [chip: Chip]; many: [chips: Chip[]] }>()
const QUIET = ['unknown', 'declined']
const picked = ref<Chip[]>([]) // multi: chips toggle, "Weiter" sends them; "Weiß nicht" still answers at once
function pick(c: Chip, multi: boolean) {
  if (!multi || QUIET.includes(c.value)) return emit('answer', c)
  picked.value = picked.value.includes(c) ? picked.value.filter((x) => x !== c) : [...picked.value, c]
}
</script>

<template>
  <section class="ask" :class="{ done: !active }">
    <h2 class="ask-h">{{ text }}</h2>
    <template v-if="active">
      <p class="why"><svg class="i" aria-hidden="true"><use href="#i-info" /></svg><span>{{ why }}</span></p>
      <div class="chips" role="group" :aria-label="text">
        <button
          v-for="c in chips"
          :key="c.value"
          type="button"
          class="chip"
          :class="{ quiet: QUIET.includes(c.value) }"
          :aria-pressed="multi && !QUIET.includes(c.value) ? picked.includes(c) : undefined"
          @click="pick(c, !!multi)"
        >
          {{ c.label }}
        </button>
      </div>
      <div v-if="multi" class="actions">
        <button type="button" class="btn btn-primary" :aria-disabled="!picked.length" @click="picked.length && emit('many', picked)">Weiter</button>
        <span class="hint">Mehrere möglich</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ask { display: grid; gap: .7rem; max-width: 40rem; padding: 1.15rem 1.25rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.ask.done { padding: .7rem 1rem; box-shadow: 0 0 0 1px var(--rule); }
.ask-h { font-size: 1.25rem; }
.ask.done .ask-h { font-size: 1rem; font-weight: 600; }
.chips { margin-top: .2rem; }
@media (forced-colors: active) { .ask { border: 1px solid CanvasText; } }
</style>
