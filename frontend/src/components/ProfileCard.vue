<script setup lang="ts">
import { computed } from 'vue'
import { k, t } from '../i18n'
import { facts, LANGS, LENGTHS, type Profile } from '../profile'

// Rendered from the current profile (not stored in the chat), so it always shows what the next reply gets.
// `compact` (in a chat): one line that opens on demand.
const props = defineProps<{ profile: Profile | null; failed: boolean; compact?: boolean }>()
// One tile per detail the Lotse can use, in the order of facts().
const ICONS: Record<string, string> = { [k('Name')]: 'i-user', [k('Adresse')]: 'i-home', [k('SV-Nummer')]: 'i-id', [k('Telefon')]: 'i-phone', [k('E-Mail')]: 'i-mail' }
const known = computed(() => (props.profile ? facts(props.profile) : []))
const missing = computed(() => Object.keys(ICONS).filter((label) => !known.value.some(([l]) => l === label)))
const total = Object.keys(ICONS).length
</script>

<template>
  <component :is="compact ? 'details' : 'div'" v-if="profile || failed" class="known" :class="{ compact }">
    <component :is="compact ? 'summary' : 'div'" class="known-h">
      <svg v-if="compact" class="i" aria-hidden="true"><use href="#i-user" /></svg>
      <svg v-else-if="profile" class="ring" viewBox="0 0 36 36" aria-hidden="true">
        <circle cx="18" cy="18" r="15.5" class="ring-bg" />
        <circle cx="18" cy="18" r="15.5" class="ring-fg" pathLength="100" :stroke-dasharray="`${(known.length / total) * 100} 100`" />
        <text x="18" y="18">{{ known.length }}/{{ total }}</text>
      </svg>
      <span class="known-t">
        <component :is="compact ? 'span' : 'h2'" class="known-title">
          {{ known.length ? t('Das weiß der Lotse über Sie') : failed ? t('Ihre Daten konnten gerade nicht geladen werden.') : t('Der Lotse weiß noch nichts über Sie.') }}<span v-if="compact && known[0]" class="muted">: {{ known[0][1] }}</span>
        </component>
        <small v-if="!compact && profile" class="muted">{{ t('{n} von {total} Angaben', { n: known.length, total }) }}</small>
      </span>
    </component>
    <ul v-if="known.length || (!compact && profile)" class="tiles">
      <li v-for="[label, value] in known" :key="label" class="tile">
        <span class="tile-i"><svg class="i" aria-hidden="true"><use :href="`#${ICONS[label]}`" /></svg></span>
        <span class="tile-t"><small>{{ t(label) }}</small><b>{{ value }}</b></span>
      </li>
      <template v-if="!compact">
        <li v-for="label in missing" :key="label">
          <a class="tile tile-add" href="#einstellungen">
            <span class="tile-i"><svg class="i" aria-hidden="true"><use :href="`#${ICONS[label]}`" /></svg></span>
            <span class="tile-t"><small>{{ t(label) }}</small><b><svg class="i" aria-hidden="true"><use href="#i-plus" /></svg>{{ t('Ergänzen') }}</b></span>
          </a>
        </li>
      </template>
    </ul>
    <p v-if="profile && !known.length" class="muted">{{ t('Mit Ihrem Namen und Ihrer Adresse kann er Anrufe und E-Mails für Sie vorbereiten.') }}</p>
    <p class="known-foot">
      <span v-if="profile" class="muted">{{ t('Antwortet auf {language}, {length}.', { language: LANGS[profile.answer_language], length: t(LENGTHS[profile.answer_length]).toLowerCase() }) }}</span>
      <a href="#einstellungen">{{ known.length ? t('Ändern') : t('Daten hinterlegen') }}</a>
    </p>
  </component>
</template>

<style scoped>
/* On the start view a white card floating on the gradient; in a chat one hairline row that opens on demand. */
.known { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; padding: 1.25rem 1.5rem 1.1rem; border-radius: var(--r-l); background: var(--sheet); color: var(--ink); --focus: var(--action); box-shadow: 0 24px 48px -24px rgba(0, 0, 0, .55); }
.known-h { display: flex; gap: .9rem; align-items: center; line-height: var(--lh); }
.known-t { display: grid; min-width: 0; }
.known-title { font-size: var(--fs-h3); font-weight: 700; line-height: 1.25; color: var(--head); }
.known-t small { font-size: var(--fs-small); }

/* Completeness ring: how many of the details the Lotse can use. */
.ring { width: 3.25rem; height: 3.25rem; flex: none; }
.ring circle { fill: none; stroke-width: 3.5; }
.ring-bg { stroke: var(--sunk); }
.ring-fg { stroke: var(--accent); stroke-linecap: round; transform: rotate(-90deg); transform-origin: center; transition: stroke-dasharray .4s cubic-bezier(.23, 1, .32, 1); }
.ring text { fill: var(--ink); font: 700 9px var(--font); text-anchor: middle; dominant-baseline: central; }

/* One tile per detail: filled ones solid, missing ones dashed and linking to the settings. */
.tiles { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 13rem), 1fr)); gap: .6rem; }
.tiles > li { display: grid; }
.tile { display: flex; align-items: center; gap: .75rem; min-width: 0; padding: .7rem .85rem; border-radius: var(--r-m); background: var(--sunk); }
.tile-i { width: 2.4rem; height: 2.4rem; flex: none; display: grid; place-items: center; border-radius: 50%; background: var(--accent-bg); color: var(--ready-ink); }
.tile-t { display: grid; min-width: 0; line-height: 1.3; }
.tile-t small { font-size: var(--fs-small); color: var(--ink-3); }
.tile-t b { font-weight: 700; overflow-wrap: anywhere; }
.tile-add { background: transparent; border: 1.5px dashed var(--rule-2); color: var(--ink-2); text-decoration: none; transition: border-color .15s, background-color .15s; }
.tile-add:hover { border-color: var(--action); background: var(--band); }
.tile-add .tile-i { background: var(--sunk); color: var(--ink-3); }
.tile-add b { display: inline-flex; align-items: center; gap: .3em; color: var(--action); }
.tile-add b .i { width: 1em; height: 1em; }

.known-foot { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; padding-top: .75rem; border-top: var(--hair); font-size: var(--fs-small); }
.known-foot a { font-weight: 600; }
[data-contrast="high"] .known:not(.compact) { box-shadow: inset 0 0 0 2px var(--ink); }
[data-contrast="high"] .tile { box-shadow: inset 0 0 0 1px var(--ink); }

.compact { gap: .6rem; padding: 0 1.1rem; border: var(--hair); box-shadow: none; }
.compact[open] { padding-bottom: 1.1rem; }
.compact .known-h { gap: .5em; min-height: 2.75rem; color: var(--ink-2); cursor: pointer; list-style: none; }
.compact .known-title { font-size: 1rem; font-weight: 400; color: inherit; }
.compact .known-h:focus-visible { outline-offset: 1px; border-radius: var(--r-s); }
.compact .known-h::-webkit-details-marker { display: none; }
.compact .known-h::after { content: ""; margin-left: auto; width: .45em; height: .45em; flex: none; border: solid var(--ink-3); border-width: 0 2px 2px 0; transform: translateY(-.15em) rotate(45deg); }
.compact[open] .known-h::after { transform: translateY(.1em) rotate(-135deg); }
.compact .known-h .i { color: var(--head); }
.compact .known-foot { padding-top: 0; border: 0; }
@media (forced-colors: active) { .tile { border: 1px solid CanvasText; } }
</style>
