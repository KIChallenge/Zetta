<script setup lang="ts">
import type { CardPayload } from '../chats'

// Fixed cards (boundary, out of scope, general): corpus text and corpus contacts only, no LLM text.
defineProps<{ card: CardPayload; text: string }>()
</script>

<template>
  <section class="notice-card" :data-card="card.card">
    <h2 class="nc-h">
      <svg class="i" aria-hidden="true"><use :href="card.card === 'boundary' ? '#i-alert' : '#i-info'" /></svg>{{ card.title }}
    </h2>
    <p>{{ text }}</p>
    <ul v-if="card.contacts.length" class="nc-list">
      <li v-for="inst in card.contacts" :key="inst.name" class="nc-inst">
        <p class="mini-h"><svg class="i" aria-hidden="true"><use href="#i-building" /></svg>{{ inst.name }}</p>
        <div v-for="ch in inst.channels" :key="ch.value" class="nc-ch">
          <a v-if="ch.href" class="nc-val" :href="ch.href">
            <svg class="i" aria-hidden="true"><use :href="ch.type === 'phone' ? '#i-phone' : ch.type === 'email' ? '#i-mail' : '#i-ext'" /></svg>{{ ch.value }}
          </a>
          <span v-else class="nc-val">{{ ch.value }}</span>
          <span v-if="ch.label" class="muted">{{ ch.label }}</span>
          <span v-if="ch.reachable?.text" class="avail" :data-open="ch.reachable.open">{{ ch.reachable.text }}</span>
          <span v-if="ch.hours" class="muted">{{ ch.hours }}</span>
        </div>
        <a class="src-link" :href="inst.source_url" target="_blank" rel="noopener noreferrer">Quelle</a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.notice-card { display: grid; gap: .75rem; max-width: 40rem; padding: 1.15rem 1.25rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.notice-card[data-card="boundary"] { box-shadow: inset 4px 0 0 var(--turn-mark), var(--lift); }
.nc-h { display: flex; gap: .5em; align-items: flex-start; font-size: 1.2rem; }
.nc-h .i { margin-top: .1em; color: var(--harbor); }
.nc-list { list-style: none; margin: 0; padding: 0; display: grid; gap: .75rem; }
.nc-inst { display: grid; gap: .4rem; padding: .85rem 1rem; border-radius: var(--r-m); background: var(--sunk); }
.nc-ch { display: flex; flex-wrap: wrap; align-items: center; gap: .2rem .9rem; }
.nc-val { display: inline-flex; align-items: center; gap: .45em; font-size: 1.15rem; font-weight: 700; color: var(--ink); text-decoration: none; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
a.nc-val:hover { color: var(--harbor); }
.nc-val .i { color: var(--harbor); }
@media (forced-colors: active) { .notice-card { border: 1px solid CanvasText; } }
</style>
