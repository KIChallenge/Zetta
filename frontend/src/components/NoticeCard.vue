<script setup lang="ts">
import type { CardPayload } from '../chats'

// Fixed cards (boundary, out of scope, general): corpus text and corpus contacts only, no LLM text.
// Name, number and "jetzt erreichbar" are shown; labels, hours, addresses and sources open under "Mehr".
defineProps<{ card: CardPayload; text: string }>()
</script>

<template>
  <section class="notice-card" :data-card="card.card">
    <h2 class="nc-h">
      <svg class="i" aria-hidden="true"><use :href="card.card === 'boundary' ? '#i-alert' : '#i-info'" /></svg>{{ card.title }}
    </h2>
    <p>{{ text }}</p>
    <template v-if="card.contacts.length">
      <ul class="nc-list">
        <li v-for="inst in card.contacts" :key="inst.name" class="nc-inst">
          <p class="mini-h">{{ inst.name }}</p>
          <template v-for="ch in inst.channels" :key="ch.value">
            <div v-if="ch.href" class="nc-ch">
              <a class="nc-val" :href="ch.href">
                <svg class="i" aria-hidden="true"><use :href="ch.type === 'phone' ? '#i-phone' : ch.type === 'email' ? '#i-mail' : '#i-ext'" /></svg>{{ ch.value }}
              </a>
              <span v-if="ch.reachable?.text" class="avail" :data-open="ch.reachable.open">{{ ch.reachable.text }}</span>
            </div>
          </template>
        </li>
      </ul>
      <details class="more">
        <summary>Mehr</summary>
        <div v-for="inst in card.contacts" :key="inst.name" class="nc-more">
          <p class="mini-h">{{ inst.name }}</p>
          <template v-for="ch in inst.channels" :key="ch.value">
            <p v-if="!ch.href">{{ ch.value }}</p>
            <p v-if="ch.label || ch.hours" class="muted">{{ [ch.label, ch.hours].filter(Boolean).join(' · ') }}</p>
          </template>
          <a class="src-link" :href="inst.source_url" target="_blank" rel="noopener noreferrer">Quelle</a>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.notice-card { display: grid; gap: .75rem; max-width: 40rem; padding: 1.15rem 1.25rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.notice-card[data-card="boundary"] { box-shadow: inset 4px 0 0 var(--turn-mark), var(--lift); }
.nc-h { display: flex; gap: .5em; align-items: flex-start; font-size: 1.2rem; }
.nc-h .i { margin-top: .1em; color: var(--harbor); }
.nc-list { list-style: none; margin: 0; padding: 0; display: grid; gap: .6rem; }
.nc-inst { display: grid; gap: .3rem; padding: .75rem 1rem; border-radius: var(--r-m); background: var(--sunk); }
.nc-ch { display: flex; flex-wrap: wrap; align-items: center; gap: .2rem .9rem; }
.nc-val { display: inline-flex; align-items: center; gap: .45em; font-size: 1.15rem; font-weight: 700; color: var(--ink); text-decoration: none; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
a.nc-val:hover { color: var(--harbor); }
.nc-val .i { color: var(--harbor); }
.nc-more { display: grid; gap: .2rem; margin-top: .6rem; font-size: .95rem; }
@media (forced-colors: active) { .notice-card { border: 1px solid CanvasText; } }
</style>
