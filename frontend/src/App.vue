<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AuthCard from './components/AuthCard.vue'
import ChatApp from './components/ChatApp.vue'
import { logout as endSession, me, type User } from './auth'
import { locale, setLocale, t } from './i18n'
import { LANGS } from './profile'
import { view } from './view'

const user = ref<User | null>(null)
// Fully translated. Once signed in, the language is a setting of the profile.
const ENTRY_LANGS = ['de', 'en', 'fr', 'cs', 'sk', 'sl'] as const
const ready = ref(false)
const atHome = ref(true) // reported by ChatApp: the footer shows on the login page and the home view
const main = ref<HTMLElement>()
const initials = computed(() =>
  (user.value?.display_name ?? '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w.charAt(0).toUpperCase()).join(''),
)

// The session cookie is invisible to scripts, so only the server can say whether someone is signed in.
me()
  .then((u) => (user.value = u))
  .catch(() => {}) // 401 or unreachable: the login screen
  .finally(() => (ready.value = true))

// The session already ended on the server (401, account deleted).
function logout() {
  user.value = null
}

// Back to the start without a chat in the URL, e.g. after the account was deleted.
function leave() {
  history.replaceState(null, '', location.pathname + location.search)
  logout()
}

function signOut() {
  endSession()
  leave()
}

// "Wie mein Gerät" follows the device, so the button needs the device's current scheme too.
const deviceDark = matchMedia('(prefers-color-scheme: dark)')
const osDark = ref(deviceDark.matches)
deviceDark.addEventListener('change', (e) => (osDark.value = e.matches))
const dark = computed(() => view.theme === 'dark' || (view.theme === 'auto' && osDark.value))

// The screen swaps under the user, so move focus to the new content.
watch(user, () => nextTick(() => main.value?.focus()))
</script>

<template>
  <!-- The hash is the router's: jump by focus, or "#inhalt" would be opened as a chat. -->
  <a class="skip" href="#inhalt" @click.prevent="main?.focus()">{{ t('Zum Inhalt springen') }}</a>
  <!-- One line on the page's own grid: signed in on wide screens, the brand cell is the sidebar's column. -->
  <header class="top" :class="{ signed: user }">
    <span class="brand">
      <!-- The mark: a "you are here" marker from hospital wayfinding. -->
      <svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="16" cy="16" r="16" class="mark-disc" /><circle cx="16" cy="16" r="8.75" class="mark-ring" /><circle cx="16" cy="16" r="3.75" class="mark-dot" />
      </svg>
      <b class="brand-t" :class="{ bl: user }">SV KI-Lotse</b>
    </span>
    <select v-if="!user" class="lang" :aria-label="t('Sprache')" :value="locale" @change="setLocale(($event.target as HTMLSelectElement).value)">
      <option v-for="code in ENTRY_LANGS" :key="code" :value="code">{{ LANGS[code] }}</option>
    </select>
    <span class="me">
      <button type="button" class="btn btn-quiet bar-btn" :title="dark ? t('Hell') : t('Dunkel')" @click="view.theme = dark ? 'light' : 'dark'">
        <svg class="i" aria-hidden="true"><use :href="dark ? '#i-sun' : '#i-moon'" /></svg><span>{{ dark ? t('Hell') : t('Dunkel') }}</span>
      </button>
      <template v-if="user">
        <a class="btn btn-quiet bar-btn bar-list" href="#gespraeche" :title="t('Alle Gespräche')">
          <svg class="i" aria-hidden="true"><use href="#i-list" /></svg><span class="xs">{{ t('Alle Gespräche') }}</span>
        </a>
        <a class="btn btn-quiet bar-btn me-btn" href="#einstellungen" :title="t('Einstellungen')">
          <span class="avatar" aria-hidden="true">{{ initials }}</span>
          <span class="me-l"><b>{{ user.display_name }}</b><small>{{ t('Einstellungen') }}</small></span>
        </a>
        <button type="button" class="btn btn-quiet bar-btn" :title="t('Abmelden')" @click="signOut">
          <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg><span>{{ t('Abmelden') }}</span>
        </button>
      </template>
    </span>
  </header>

  <main id="inhalt" ref="main" :class="user ? 'signed-in' : 'entry'" tabindex="-1">
    <template v-if="ready">
      <ChatApp v-if="user" :user="user" @expired="logout" @deleted="leave" @home="atHome = $event" />
      <template v-else>
        <div class="entry-text">
          <!-- avoid-ai-design-ignore: SD5 (two-weight headline: a bold first line, as asked in the brief) -->
          <h1 class="entry-h"><b>{{ t('Ihr Wegweiser') }}</b> {{ t('durch die Sozialversicherung') }}</h1>
          <p class="entry-lead">{{ t('Beschreiben Sie Ihr Anliegen. Der Lotse sagt Ihnen, wen Sie anrufen und was Sie mitbringen.') }}</p>
        </div>
        <div class="entry-side">
          <AuthCard @done="user = $event" />
        </div>
      </template>
    </template>
  </main>

  <!-- Navy, like the home pane: it frames the app opposite the white bar. Contacts as the Lotse's medical card
       names them; institution names stay German, as everywhere. -->
  <footer v-if="ready && (!user || atHome)" class="foot navy-band">
    <span class="foot-brand" aria-hidden="true">
      <svg class="foot-mark" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" class="fm-ring" /><circle cx="16" cy="16" r="5" class="fm-dot" /></svg>SV KI-Lotse
    </span>
    <span class="foot-call">
      <span class="foot-l">{{ t('Medizinische Fragen:') }}</span>
      <a class="tel" href="tel:1450"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg><b>1450</b><span class="long">Gesundheitsberatung</span></a>
    </span>
    <span class="foot-call">
      <span class="foot-l">{{ t('Im Notfall:') }}</span>
      <a class="tel" href="tel:144"><svg class="i" aria-hidden="true"><use href="#i-phone" /></svg><b>144</b><span class="long">Rettungsnotruf</span></a>
    </span>
  </footer>
</template>

<style scoped>
.lang { width: auto; min-height: 2.5rem; margin-left: auto; padding: .3rem .6rem; }
/* One line, a hairline under it like the rest of the app. The logo sits where the sidebar's content starts. */
.top { display: flex; align-items: center; justify-content: space-between; gap: .75rem 1rem; min-height: 3.5rem; padding: .4rem 1.25rem .4rem 1rem; background: var(--paper); border-bottom: var(--hair); }
.brand { display: flex; align-items: center; gap: .7rem; min-width: 0; }
.mark { width: 2.25rem; height: 2.25rem; flex: none; }
.mark-disc { fill: var(--navy); }
.mark-ring { fill: none; stroke: var(--on-navy); stroke-width: 2.5; }
.mark-dot { fill: var(--ready-mark); }
[data-scheme="dark"] .mark-disc { fill: var(--on-navy); }
[data-scheme="dark"] .mark-ring { stroke: var(--paper); }
.brand-t { font-size: var(--fs-h3); font-weight: 700; line-height: 1.15; color: var(--ink); }
.me { display: inline-flex; align-items: center; gap: .25rem .5rem; }
.me-btn { padding-inline: .35rem .9rem; }
.avatar { width: 2.25rem; height: 2.25rem; flex: none; border-radius: 50%; background: var(--accent); color: var(--paper); display: grid; place-items: center; font-weight: 700; font-size: var(--fs-small); }
.me-l b { display: block; color: var(--ink); }
.me-l small { display: block; font-size: var(--fs-small); font-weight: 600; }
/* Bar buttons are full-height targets, so the focus ring sits inside the bar. */
.bar-btn:focus-visible { outline-offset: 0; }

main { display: grid; min-height: 0; overflow-y: auto; }
/* Footer: a navy band with the two numbers anyone may need, as outlined pills that call. */
.foot { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem 1.75rem; padding: .45rem 1.25rem .45rem 1rem; }
.foot-brand { display: inline-flex; align-items: center; gap: .55rem; margin-right: auto; font-weight: 700; color: var(--on-navy-2); }
.foot-mark { width: 1.5rem; height: 1.5rem; }
.fm-ring { fill: none; stroke: currentColor; stroke-width: 2.5; }
.fm-dot { fill: var(--ready-mark); }
.foot-call { display: inline-flex; align-items: center; gap: .65rem; }
.foot-l { font-size: var(--fs-small); color: var(--on-navy-2); }
.tel { display: inline-flex; align-items: center; gap: .45rem; min-height: 2.25rem; padding: .15rem .95rem .15rem .75rem; border: 1px solid var(--on-navy-2); border-radius: var(--r-pill); color: var(--on-navy); text-decoration: none; font-variant-numeric: tabular-nums; transition: background-color .15s; }
.tel:hover { background: color-mix(in srgb, var(--on-navy) 12%, transparent); }
.tel b { font-size: var(--fs-lead); line-height: 1; }
.tel .long { font-size: var(--fs-small); color: var(--on-navy-2); }
[data-contrast="high"] .tel { border-width: 2px; border-color: var(--on-navy); }
/* Focus moves here only to restart reading after a screen change; a ring around the whole page says nothing. */
main:focus-visible { outline: none; }
.signed-in { grid-template-rows: minmax(0, 1fr); }

/* Entry: a calm headline beside the login card, stacked on narrow screens. */
.entry { grid-template-columns: minmax(0, 1fr); align-content: start; }
.entry-text { min-width: 0; display: grid; align-content: center; gap: 1.25rem; padding: clamp(1.75rem, 6vh, 3.5rem) clamp(1rem, 6vw, 4rem); }
.entry-h { font-size: clamp(var(--fs-h1), 6cqi, var(--fs-display)); line-height: 1.15; hyphens: auto; overflow-wrap: break-word; }
.entry-h b { display: block; font-weight: 700; }
.entry-lead { max-width: 30rem; font-size: var(--fs-lead); color: var(--ink-2); }
.entry-side { display: grid; place-items: center; padding: clamp(1.5rem, 5vh, 3rem) clamp(1rem, 4vw, 2.5rem); background: var(--accent-bg); }
@container (min-width: 56rem) {
  .entry { grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-content: stretch; }
}

@container (min-width: 56rem) {
  .bar-list { display: none; }
  /* Signed in: the bar follows the page's two columns. The brand cell is the sidebar's width and its hairline runs
     on up through the bar; the buttons sit at the right edge. */
  .top.signed { display: grid; grid-template-columns: 20rem minmax(0, 1fr); padding: 0; }
  .top.signed .brand { align-self: stretch; padding: .4rem 1rem; border-right: var(--hair); }
  .top.signed .me { justify-self: end; padding: .4rem 1.25rem; }
}
/* Narrow, signed in: round icon buttons with a short label underneath. */
@container (max-width: 55.99rem) {
  .bl, .me-l b { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .me { gap: .15rem; }
  .bar-btn { flex-direction: column; gap: .2rem; min-height: 0; padding: .15rem .35rem; border-radius: var(--r-m); font-size: var(--fs-meta); font-weight: 600; }
  .bar-btn .i { box-sizing: content-box; width: 1.2rem; height: 1.2rem; padding: .45rem; border: 1px solid var(--rule-2); border-radius: 50%; }
  .avatar { width: calc(1.2rem + .9rem + 2px); height: calc(1.2rem + .9rem + 2px); }
  .me-l small { font-size: inherit; }
  /* Narrow, the footer is just the two pills: labels and names stay for screen readers. */
  .foot-brand { display: none; }
  .foot :is(.foot-l, .long) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .foot { justify-content: center; gap: .5rem 1rem; padding: .5rem 1rem; }
}
/* Phone: the list link shows only its icon and the spacing tightens, so four buttons fit one row. */
@container (max-width: 23.99rem) {
  .top { padding-inline: .5rem; }
  .me { gap: 0; }
  .bar-btn { padding-inline: .1rem; }
  .xs, .brand-t { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
}
/* Phone at text size XL: the labels no longer fit under the icons, so screen readers keep them and the icons stay. */
@container (max-width: 17.99rem) {
  .bar-btn > span:not(.avatar) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
}
</style>
