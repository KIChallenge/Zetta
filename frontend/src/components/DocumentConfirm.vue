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
  <section class="confirm" :class="{ done: !active }">
    <h2 class="confirm-h">{{ text }}</h2>
    <template v-if="active && payload.items.length">
      <ul class="checks">
        <li v-for="i in payload.items" :key="i.recommendation">
          <label class="check">
            <input v-model="picked" type="checkbox" :value="i.recommendation" />
            <span><b>{{ i.label }}</b><small>„{{ i.quote }}“</small></span>
          </label>
        </li>
      </ul>
      <p class="hint">Befunde liest der Lotse nicht. Ihr Brief wird nicht gespeichert.</p>
      <div class="actions"><button type="button" class="btn btn-primary" @click="confirm">Stimmt so, weiter</button></div>
    </template>
    <!-- Answered: the quotes are in the plan, here only what the letter contained. -->
    <ul v-else-if="payload.items.length" class="found">
      <li v-for="i in payload.items" :key="i.recommendation">{{ i.label }}</li>
    </ul>
  </section>
</template>

<style scoped>
.confirm { display: grid; gap: .8rem; max-width: 40rem; padding: 1.15rem 1.25rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.confirm-h { font-size: 1.15rem; }
.confirm.done { gap: .4rem; padding: .7rem 1rem; box-shadow: 0 0 0 1px var(--rule); }
.confirm.done .confirm-h { font-size: 1rem; font-weight: 600; }
.found { margin: 0; padding-left: 1.2rem; color: var(--ink-2); }
@media (forced-colors: active) { .confirm { border: 1px solid CanvasText; } }
</style>
