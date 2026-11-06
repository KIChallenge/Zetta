<script setup lang="ts">
import { ref } from 'vue'
import type { Chip } from '../chats'
import { t } from '../i18n'

// One question at a time. Only the latest one has chips; answered ones stay as plain text in the history.
// `note`: the line after an off-topic message, before the open question is asked again.
defineProps<{ text: string; why: string; chips: Chip[]; active: boolean; multi?: boolean; note?: string }>()
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
    <p v-if="note && active">{{ note }}</p>
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
          {{ t(c.label) }}
        </button>
      </div>
      <div v-if="multi" class="actions">
        <button type="button" class="btn btn-primary" :aria-disabled="!picked.length" @click="picked.length && emit('many', picked)">{{ t('Weiter') }}</button>
        <span class="hint">{{ t('Mehrere möglich') }}</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* A Lotse speech bubble on navy, like its text replies. The open question carries the chips;
   answered ones shrink to the question alone. */
.ask { position: relative; display: grid; gap: .8rem; max-width: 40rem; margin-bottom: .7rem; padding: 1.1rem 1.3rem 1.3rem; border-radius: var(--r-s); background: var(--navy); color: var(--on-navy); --focus: var(--on-navy); }
.ask::after { content: ""; position: absolute; left: 1.25rem; bottom: -.7rem; width: 1.1rem; height: .75rem; background: var(--navy); clip-path: polygon(0 0, 100% 0, 0 100%); }
.ask-h { font-size: var(--fs-h3); font-weight: 600; color: inherit; }
.ask.done { justify-self: start; width: fit-content; padding: .75rem 1.1rem; }
.ask.done .ask-h { font-size: 1rem; font-weight: 400; }
.why { color: var(--on-navy-2); }
.why .i { color: var(--on-navy); }
.hint { color: var(--on-navy-2); }
.chips { margin-top: .2rem; }
.chip:focus-visible { outline-offset: 2px; }
/* Pressed chips stay blue (green is never a button); the white edge keeps them apart from the navy. */
.chip[aria-pressed="true"] { border-color: var(--on-navy); }
.btn-primary { background: var(--on-navy); color: var(--navy); }
.btn-primary:hover { background: var(--on-navy-2); }
[data-contrast="high"] .ask { box-shadow: inset 0 0 0 2px var(--on-navy); }
@media (forced-colors: active) { .ask { border: 1px solid CanvasText; } }
</style>
