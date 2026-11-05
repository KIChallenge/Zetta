<script setup lang="ts">
import { ref } from 'vue'
import type { Chip, Fact } from '../chats'

// "Verstanden": what the plan is based on. Tapping a fact offers its values; a pick is sent like a chip answer.
defineProps<{ facts: Fact[]; disabled: boolean }>()
const emit = defineEmits<{ answer: [fact: Fact, chip: Chip] }>()
const editing = ref<string | null>(null)
const same = (f: Fact, c: Chip) => (Array.isArray(f.value) ? f.value.length === 1 && f.value[0] === c.value : f.value === c.value)

function pick(f: Fact, c: Chip) {
  editing.value = null
  if (!same(f, c)) emit('answer', f, c)
}
</script>

<template>
  <section class="facts" aria-labelledby="facts-h">
    <h2 id="facts-h" class="facts-h">Verstanden</h2>
    <ul class="fact-list">
      <li v-for="f in facts" :key="f.key">
        <button
          type="button"
          class="fact"
          :aria-expanded="editing === f.key"
          :aria-controls="`fe-${f.key}`"
          :disabled="disabled"
          @click="editing = editing === f.key ? null : f.key"
        >
          <span class="fact-k">{{ f.label }}</span>
          <b>{{ f.value_label }}</b>
          <svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg>
          <span class="sr"> ändern</span>
        </button>
      </li>
    </ul>
    <template v-for="f in facts" :key="f.key">
      <div v-if="editing === f.key" :id="`fe-${f.key}`" class="fact-edit">
        <p class="mini-h">{{ f.label }} ändern<span v-if="f.source === 'profile'" class="muted">bisher aus Ihren Daten</span></p>
        <div class="chips">
          <button
            v-for="c in f.chips"
            :key="c.value"
            type="button"
            class="chip"
            :aria-pressed="same(f, c)"
            @click="pick(f, c)"
          >
            {{ c.label }}
          </button>
        </div>
      </div>
    </template>
    <p class="hint">Stimmt etwas nicht? Tippen Sie darauf, dann passt der Lotse den Plan an.</p>
  </section>
</template>

<style scoped>
.facts { display: grid; gap: .6rem; max-width: 44rem; }
.facts-h { font-size: .95rem; color: var(--ink-3); }
.fact-list { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: .45rem; }
.fact { display: inline-flex; align-items: center; gap: .45em; min-height: 2.5rem; padding: .3rem .8rem; border: 1px solid var(--rule-2); border-radius: 999px; background: var(--sheet); color: var(--ink); font: inherit; font-size: .95rem; cursor: pointer; }
.fact:hover, .fact[aria-expanded="true"] { border-color: var(--harbor); color: var(--harbor); }
.fact:disabled { cursor: progress; opacity: .7; }
.fact-k { color: var(--ink-3); }
.fact .i { width: 1em; height: 1em; color: var(--ink-3); }
.fact-edit { display: grid; gap: .6rem; padding: .9rem 1rem; border-radius: var(--r-m); background: var(--sunk); }
</style>
