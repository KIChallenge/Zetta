<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FormBody, Prefill } from '../chats'
import { t } from '../i18n'
import DetailInputs from './DetailInputs.vue'

// Asks right on the form card for the details the form still needs and keeps them for the next forms. Only a few at
// once, those that fill the most fields (the backend sorts them): the next forms ask for the rest.
const FIRST = 5

const props = defineProps<{ prefill: Prefill; title: string }>()
const emit = defineEmits<{ submit: [body: FormBody] }>()

const remember = ref(true)
const all = ref(false)
const inputs = ref<InstanceType<typeof DetailInputs>>()
const shown = computed(() => (all.value ? props.prefill.ask : props.prefill.ask.slice(0, FIRST)))
const more = computed(() => props.prefill.ask.length - shown.value.length)
const percent = computed(() => {
  const { done, total } = props.prefill
  return total ? Math.round((100 * done) / total) : 100
})

function submit() {
  const entered = inputs.value ? inputs.value.collect() : {}
  if (!entered) return
  emit('submit', { user: entered.user ?? {}, subject: entered.subject ?? {}, remember: remember.value })
}
</script>

<template>
  <form class="ff" novalidate @submit.prevent="submit">
    <div class="ff-meter">
      <p class="ff-count"><b>{{ t('{done} von {total} Feldern ausgefüllt', { done: prefill.done, total: prefill.total }) }}</b></p>
      <div class="bar" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100" :aria-label="t('Schon ausgefüllt')"><span :style="{ width: `${percent}%` }" /></div>
      <p v-if="prefill.filled.length" class="hint">{{ t('Schon eingetragen:') }} {{ prefill.filled.map((l) => t(l)).join(', ') }}.</p>
    </div>

    <template v-if="prefill.ask.length">
      <p class="mini-h">{{ t('Für dieses Formular fehlt noch:') }}</p>
      <DetailInputs ref="inputs" :entries="shown" scope="user" own />
      <button v-if="more" type="button" class="linkbtn more" @click="all = true">{{ t('Weitere Angaben ({n})', { n: more }) }}</button>
      <label class="check">
        <input v-model="remember" type="checkbox" />
        <span><b>{{ t('Für weitere Anträge merken') }}</b><small>{{ t('Dann sind diese Angaben im nächsten Formular schon eingetragen. Sie können sie in den Einstellungen ändern oder löschen.') }}</small></span>
      </label>
    </template>

    <div class="actions">
      <button type="submit" class="btn btn-primary"><svg class="i" aria-hidden="true"><use href="#i-file" /></svg>{{ title }} (PDF, {{ t('vorausgefüllt') }})</button>
    </div>
    <p v-if="prefill.ask.length" class="hint">{{ t('Was Sie leer lassen, schreiben Sie selbst ins Formular.') }}</p>
  </form>
</template>

<style scoped>
.ff { display: grid; gap: 1rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
.ff-meter { display: grid; gap: .4rem; }
.ff-count { margin: 0; }
.bar { height: .5rem; border-radius: var(--r-pill); background: var(--rule-2); overflow: hidden; }
.bar span { display: block; height: 100%; background: var(--accent); transition: width .4s cubic-bezier(.23, 1, .32, 1); }
.more { justify-self: start; min-height: 2.75rem; font-weight: 600; }
.check { background: var(--sheet); }
.check span { display: grid; gap: .15rem; }
.check small { color: var(--ink-2); }
.actions { display: flex; flex-wrap: wrap; gap: .6rem; }
[data-contrast="high"] .ff { box-shadow: inset 0 0 0 1px var(--ink); }
</style>
