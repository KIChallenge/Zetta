<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../i18n'
import { facts, LANGS, LENGTHS, type Profile } from '../profile'

// Rendered from the current profile (not stored in the chat), so it always shows what the next reply gets.
// `compact` (in a chat): one line that opens on demand.
const props = defineProps<{ profile: Profile | null; failed: boolean; compact?: boolean }>()
const known = computed(() => (props.profile ? facts(props.profile) : []))
</script>

<template>
  <component :is="compact ? 'details' : 'div'" v-if="profile || failed" class="known" :class="{ compact }">
    <component :is="compact ? 'summary' : 'h2'" class="known-h">
      <svg class="i" aria-hidden="true"><use href="#i-user" /></svg>
      <span>
        {{ known.length ? t('Das weiß der Lotse über Sie') : failed ? t('Ihre Daten konnten gerade nicht geladen werden.') : t('Der Lotse weiß noch nichts über Sie.') }}<span v-if="compact && known[0]" class="muted">: {{ known[0][1] }}</span>
      </span>
    </component>
    <dl v-if="known.length" class="kv">
      <div v-for="[k, v] in known" :key="k"><dt>{{ t(k) }}</dt><dd>{{ v }}</dd></div>
    </dl>
    <p v-else-if="profile" class="muted">{{ t('Mit Ihrem Namen und Ihrer Adresse kann er Anrufe und E-Mails für Sie vorbereiten.') }}</p>
    <p class="known-foot">
      <span v-if="profile" class="muted">{{ t('Antwortet auf {language}, {length}.', { language: LANGS[profile.answer_language], length: t(LENGTHS[profile.answer_length]).toLowerCase() }) }}</span>
      <a href="#einstellungen">{{ known.length ? t('Ändern') : t('Daten hinterlegen') }}</a>
    </p>
  </component>
</template>

<style scoped>
/* On the start view a grey ground block; in a chat one hairline row that opens on demand. */
.known { display: grid; grid-template-columns: minmax(0, 1fr); gap: .6rem; padding: 1.1rem 1.25rem; border-radius: var(--r-m); background: var(--sunk); }
.known-h { display: flex; gap: .5em; align-items: flex-start; font-size: 1rem; font-weight: 700; line-height: var(--lh); }
.known-h .i { margin-top: .15em; color: var(--head); }
.compact { padding: 0 1.1rem; border: var(--hair); background: var(--sheet); }
.compact[open] { padding-bottom: 1.1rem; }
.compact .known-h { align-items: center; min-height: 2.75rem; font-weight: 400; color: var(--ink-2); cursor: pointer; list-style: none; }
.compact .known-h:focus-visible { outline-offset: 1px; border-radius: var(--r-s); }
.compact .known-h::-webkit-details-marker { display: none; }
.compact .known-h::after { content: ""; margin-left: auto; width: .45em; height: .45em; flex: none; border: solid var(--ink-3); border-width: 0 2px 2px 0; transform: translateY(-.15em) rotate(45deg); }
.compact[open] .known-h::after { transform: translateY(.1em) rotate(-135deg); }
.compact .known-h .i { margin-top: 0; }
.kv { margin: 0; display: grid; gap: .35rem; }
.kv div { display: flex; flex-wrap: wrap; gap: 0 1rem; }
.kv dt { flex: 0 0 6.5rem; color: var(--ink-3); }
.kv dd { flex: 1 1 12rem; min-width: 0; margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.known-foot { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; font-size: var(--fs-small); }
.known-foot a { font-weight: 600; }
[data-contrast="high"] .known:not(.compact) { box-shadow: inset 0 0 0 1px var(--ink); }
</style>
