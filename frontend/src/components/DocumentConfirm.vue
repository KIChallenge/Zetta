<script setup lang="ts">
import { ref } from 'vue'
import type { ConfirmPayload } from '../chats'

// Quotes found in the letter: the user confirms which are right. Only confirmed ones shape the plan.
const props = defineProps<{ text: string; payload: ConfirmPayload; active: boolean }>()
const emit = defineEmits<{ confirm: [values: string[], labels: string[]] }>()
const picked = ref(props.payload.items.map((i) => i.recommendation))

function confirm() {
  const items = props.payload.items.filter((i) => picked.value.includes(i.recommendation))
  emit('confirm', items.map((i) => i.recommendation), items.map((i) => i.label))
}
</script>

<template>
  <section class="confirm">
    <h2 class="confirm-h">{{ text }}</h2>
    <ul v-if="payload.items.length" class="checks">
      <li v-for="i in payload.items" :key="i.recommendation">
        <label class="check">
          <input v-model="picked" type="checkbox" :value="i.recommendation" :disabled="!active" />
          <span><b>{{ i.label }}</b><small>In Ihrem Brief steht: „{{ i.quote }}“</small></span>
        </label>
      </li>
    </ul>
    <template v-if="active && payload.items.length">
      <p class="hint">Der Lotse liest nur Empfehlungen zu Anträgen und Unterstützung, keine Befunde. Ihr Brief selbst wird nicht gespeichert.</p>
      <div class="actions"><button type="button" class="btn btn-primary" @click="confirm">Stimmt so, weiter</button></div>
    </template>
  </section>
</template>

<style scoped>
.confirm { display: grid; gap: .8rem; max-width: 40rem; padding: 1.15rem 1.25rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.confirm-h { font-size: 1.15rem; }
@media (forced-colors: active) { .confirm { border: 1px solid CanvasText; } }
</style>
