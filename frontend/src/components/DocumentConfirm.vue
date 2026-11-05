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
.confirm { display: grid; gap: .85rem; max-width: 40rem; padding: 1.25rem 1.4rem 1.4rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
.confirm-h { font-size: var(--fs-h3); font-weight: 600; color: var(--head); }
.confirm.done { gap: .4rem; padding: 0; border: 0; background: none; }
.confirm.done .confirm-h { font-size: 1rem; color: var(--ink-2); }
.confirm .btn:focus-visible { outline-offset: 2px; }
.found { margin: 0; padding-left: 1.2rem; color: var(--ink-2); }
</style>
