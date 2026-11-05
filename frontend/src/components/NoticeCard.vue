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
.notice-card { display: grid; gap: .8rem; max-width: 40rem; padding: 1.25rem 1.4rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
/* Boundary (not a medical answer): the "your turn" tone, since the next step is the user's. */
.notice-card[data-card="boundary"] { border: 2px solid var(--turn-mark); }
.notice-card[data-card="boundary"] .nc-h .i { color: var(--turn-mark); }
.nc-h { display: flex; gap: .5em; align-items: flex-start; font-size: var(--fs-h3); font-weight: 600; color: var(--head); }
.nc-h .i { margin-top: .1em; color: var(--head); }
.nc-list { list-style: none; margin: 0; padding: 0; display: grid; }
.nc-inst { display: grid; gap: .35rem; padding-block: .85rem; border-top: var(--hair); }
.nc-ch { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .9rem; }
.nc-val { display: inline-flex; align-items: center; gap: .45em; font-size: var(--fs-lead); font-weight: 600; color: var(--head); text-decoration: none; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
a.nc-val:hover { text-decoration: underline; }
.nc-val:focus-visible { outline-offset: 2px; }
.nc-more { display: grid; gap: .2rem; margin-top: .6rem; font-size: var(--fs-small); }
</style>
