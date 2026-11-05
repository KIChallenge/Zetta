<script setup lang="ts">
import type { Chip } from '../chats'

// One question at a time. Only the latest one has chips; answered ones stay as plain text in the history.
defineProps<{ text: string; why: string; chips: Chip[]; active: boolean }>()
const emit = defineEmits<{ answer: [chip: Chip] }>()
const QUIET = ['unknown', 'declined']
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
          @click="emit('answer', c)"
        >
          {{ c.label }}
        </button>
      </div>
      <p class="hint">Oder schreiben Sie Ihre Antwort unten ins Textfeld.</p>
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
