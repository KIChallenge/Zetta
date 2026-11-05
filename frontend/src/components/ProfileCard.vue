<script setup lang="ts">
import { computed } from 'vue'
import { facts, LANGS, LENGTHS, type Profile } from '../profile'

// Rendered from the current profile (not stored in the chat), so it always shows what the next reply gets.
const props = defineProps<{ profile: Profile | null; failed: boolean }>()
const known = computed(() => (props.profile ? facts(props.profile) : []))
</script>

<template>
  <div v-if="profile || failed" class="known">
    <h2 class="known-h">
      <svg class="i" aria-hidden="true"><use href="#i-user" /></svg>
      {{ known.length ? 'Das weiß der Lotse über Sie' : failed ? 'Ihre Daten konnten gerade nicht geladen werden.' : 'Der Lotse weiß noch nichts über Sie.' }}
    </h2>
    <dl v-if="known.length" class="kv">
      <div v-for="[k, v] in known" :key="k"><dt>{{ k }}</dt><dd>{{ v }}</dd></div>
    </dl>
    <p v-else-if="profile" class="muted">Mit Ihrem Namen und Ihrer Adresse kann er Anrufe und E-Mails für Sie vorbereiten.</p>
    <p class="known-foot">
      <span v-if="profile" class="muted">Antwortet auf {{ LANGS[profile.answer_language] }}, {{ LENGTHS[profile.answer_length].toLowerCase() }}.</span>
      <a href="#einstellungen">{{ known.length ? 'Ändern' : 'Daten hinterlegen' }}</a>
    </p>
  </div>
</template>

<style scoped>
.known { display: grid; grid-template-columns: minmax(0, 1fr); gap: .6rem; padding: 1rem 1.15rem; border-radius: var(--r-l); background: var(--sheet); box-shadow: var(--lift); }
.known-h { display: flex; gap: .5em; align-items: flex-start; font-size: 1rem; line-height: var(--lh); }
.known-h .i { margin-top: .15em; color: var(--harbor); }
.kv { margin: 0; display: grid; gap: .35rem; }
.kv div { display: flex; flex-wrap: wrap; gap: 0 1rem; }
.kv dt { flex: 0 0 6.5rem; color: var(--ink-3); }
.kv dd { flex: 1 1 12rem; min-width: 0; margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.known-foot { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; font-size: .95rem; }
.known-foot a { color: var(--harbor); font-weight: 600; text-underline-offset: .2em; }
@media (forced-colors: active) { .known { border: 1px solid CanvasText; } }
</style>
