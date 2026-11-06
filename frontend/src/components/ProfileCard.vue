<script setup lang="ts">
import { computed } from 'vue'
import { k, t } from '../i18n'
import { facts, LANGS, LENGTHS, type Profile } from '../profile'

// Rendered from the current profile (not stored in the chat), so it always shows what the next reply gets.
// `compact` (in a chat): one line that opens on demand. On the start view every detail gets a row, missing ones link to the settings.
const props = defineProps<{ profile: Profile | null; failed: boolean; compact?: boolean }>()
const all = computed(() => (props.profile ? facts(props.profile) : []))
const known = computed(() => all.value.filter(([, v]) => v))
const rows = computed(() => (props.compact ? known.value : all.value))
const ICONS: Record<string, string> = { [k('Name')]: 'i-user', [k('Adresse')]: 'i-home', [k('SV-Nummer')]: 'i-id', [k('Telefon')]: 'i-phone', [k('E-Mail')]: 'i-mail' }
</script>

<template>
  <component :is="compact ? 'details' : 'div'" v-if="profile || failed" class="known" :class="compact ? 'compact' : 'start'">
    <component :is="compact ? 'summary' : 'h2'" class="known-h">
      <svg v-if="compact" class="i" aria-hidden="true"><use href="#i-user" /></svg>
      <span>
        {{ known.length ? t('Das weiß Zetta über Sie') : failed ? t('Ihre Daten konnten gerade nicht geladen werden.') : t('Zetta weiß noch nichts über Sie.') }}<span v-if="compact && known[0]" class="muted">: {{ known[0][1] }}</span>
      </span>
    </component>
    <dl v-if="rows.length" class="kv">
      <div v-for="([label, value], i) in rows" :key="label" :class="{ empty: !value }">
        <dt :id="`kv-${i}`"><svg v-if="!compact" class="i" aria-hidden="true"><use :href="`#${ICONS[label]}`" /></svg>{{ t(label) }}</dt>
        <dd v-if="value">{{ value }}</dd>
        <dd v-else>
          <a :id="`kv-${i}-a`" href="#einstellungen" :aria-labelledby="`kv-${i} kv-${i}-a`"><svg class="i" aria-hidden="true"><use href="#i-plus" /></svg>{{ t('Ergänzen') }}</a>
        </dd>
      </div>
    </dl>
    <p v-if="profile && !known.length" class="muted">{{ t('Mit Ihrem Namen und Ihrer Adresse kann er Anrufe und E-Mails für Sie vorbereiten.') }}</p>
    <p class="known-foot">
      <span v-if="profile" class="muted">{{ t('Antwortet auf {language}, {length}.', { language: LANGS[profile.answer_language], length: t(LENGTHS[profile.answer_length]).toLowerCase() }) }}</span>
      <a href="#einstellungen">{{ known.length ? t('Ändern') : t('Daten hinterlegen') }}</a>
    </p>
  </component>
</template>

<style scoped>
.known { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; } /* stretched to a tall column, the rows stay together */
.known-h { display: flex; gap: .5em; align-items: center; line-height: 1.25; }
.kv { margin: 0; display: grid; }
.kv dd { min-width: 0; margin: 0; font-weight: 600; overflow-wrap: anywhere; }
.known-foot { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: .25rem 1rem; font-size: var(--fs-small); }
.known-foot a { font-weight: 600; }

/* Start view: right on the navy pane, so the white composer above stays the one thing to use.
   Like a filled-in form, since these details go into the forms: one field per detail, the value on its line;
   an empty field is a dashed blank line that links to the settings. */
.start { gap: 1rem; color: var(--on-navy); }
.start .known-h { font-size: 1rem; font-weight: 700; }
.start .kv { grid-template-columns: repeat(auto-fill, minmax(min(100%, 10rem), 1fr)); gap: 1rem 1.5rem; }
.start .kv div { display: grid; align-content: space-between; gap: .2rem; padding-bottom: .4rem; border-bottom: 1px solid var(--rule-2); }
.start .kv .empty { border-bottom-style: dashed; }
.start .kv dt { display: flex; align-items: center; gap: .4em; font-size: var(--fs-small); color: var(--on-navy-2); }
.start a { color: var(--on-navy); }
.start .kv dd a { display: inline-flex; align-items: center; gap: .3em; text-decoration: none; }
.start .kv dd a:hover { text-decoration: underline; }
.start .kv dd a .i { width: 1em; height: 1em; }
.start .muted { color: var(--on-navy-2); }
[data-contrast="high"] .start .kv div { border-bottom-color: var(--on-navy); }

/* In a chat: one hairline row that opens on demand. */
.compact { gap: .6rem; padding: 0 1.1rem; border: var(--hair); border-radius: var(--r-m); background: var(--sheet); }
.compact[open] { padding-bottom: 1.1rem; }
.compact .known-h { min-height: 2.75rem; color: var(--ink-2); cursor: pointer; list-style: none; }
.compact .known-h .i { color: var(--head); }
.compact .known-h:focus-visible { outline-offset: 1px; border-radius: var(--r-s); }
.compact .known-h::-webkit-details-marker { display: none; }
.compact .known-h::after { content: ""; margin-left: auto; width: .45em; height: .45em; flex: none; border: solid var(--ink-3); border-width: 0 2px 2px 0; transform: translateY(-.15em) rotate(45deg); }
.compact[open] .known-h::after { transform: translateY(.1em) rotate(-135deg); }
.compact .kv { gap: .35rem; }
.compact .kv div { display: flex; flex-wrap: wrap; gap: 0 1rem; }
.compact .kv dt { flex: 0 0 6.5rem; color: var(--ink-3); }
.compact .kv dd { flex: 1 1 12rem; }
</style>
