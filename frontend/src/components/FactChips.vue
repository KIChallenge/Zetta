<script setup lang="ts">
import { ref } from 'vue'
import type { Chip, Fact } from '../chats'

// "Verstanden": what the plan is based on, in one line. "Ändern" opens the facts; a pick is sent like a chip answer.
defineProps<{ facts: Fact[]; disabled: boolean }>()
const emit = defineEmits<{ answer: [fact: Fact, chip: Chip] }>()
const open = ref(false)
const editing = ref<string | null>(null)
const same = (f: Fact, c: Chip) => (Array.isArray(f.value) ? f.value.length === 1 && f.value[0] === c.value : f.value === c.value)
// The letter's recommendations are listed in the confirm card already; here only their number.
const shown = (f: Fact) =>
  f.key === 'documented_recommendations' && Array.isArray(f.value) ? `${f.value.length} Empfehlungen` : f.value_label

function pick(f: Fact, c: Chip) {
  editing.value = null
  open.value = false
  if (!same(f, c)) emit('answer', f, c)
}
</script>

<template>
  <section class="facts" aria-labelledby="facts-h">
    <p class="facts-line">
      <span id="facts-h" class="facts-ok"><svg class="i" aria-hidden="true"><use href="#i-check" /></svg>Verstanden:</span>
      <template v-for="(f, i) in facts" :key="f.key">
        <span v-if="i" class="sep" aria-hidden="true">·</span>
        <span><span class="fact-k">{{ f.label }}: </span><b>{{ shown(f) }}</b></span>
      </template>
      <button type="button" class="linkbtn" :aria-expanded="open" aria-controls="facts-edit" :disabled="disabled" @click="open = !open">
        <svg class="i" aria-hidden="true"><use href="#i-pencil" /></svg>Ändern
      </button>
    </p>
    <div v-if="open" id="facts-edit" class="facts-edit">
      <p class="hint">Was stimmt nicht?</p>
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
            <b>{{ shown(f) }}</b>
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
    </div>
  </section>
</template>

<style scoped>
.facts { display: grid; gap: .6rem; max-width: 44rem; }
.facts-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: .15rem .5rem; color: var(--ink-2); }
.facts-line b { color: var(--ink); font-weight: 600; }
.facts-ok { display: inline-flex; align-items: center; gap: .3em; align-self: center; color: var(--accent); font-weight: 700; }
.sep, .fact-k { color: var(--ink-3); }
.facts-line .linkbtn { display: inline-flex; align-items: center; gap: .3em; min-height: 2.75rem; font-weight: 600; }
.facts-line .linkbtn:disabled { cursor: progress; opacity: .7; }
.facts-line .linkbtn .i { width: 1em; height: 1em; }
.facts-edit { display: grid; gap: .6rem; }
.fact-list { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: .5rem; }
.fact { display: inline-flex; align-items: center; gap: .45em; min-height: 2.75rem; padding: .3rem 1rem; border: 1px solid var(--rule-2); border-radius: var(--r-pill); background: var(--sheet); color: var(--ink); font: inherit; cursor: pointer; transition: border-color .15s, background-color .15s; }
.fact:hover, .fact[aria-expanded="true"] { border-color: var(--action); background: var(--band); }
.fact:focus-visible { outline-offset: 2px; }
.fact:disabled { cursor: progress; opacity: .7; }
.fact-edit { display: grid; gap: .6rem; padding: 1rem 1.1rem; border-radius: var(--r-m); background: var(--sunk); }
[data-contrast="high"] .fact-edit { box-shadow: inset 0 0 0 1px var(--ink); }
</style>
