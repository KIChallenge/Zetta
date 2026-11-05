<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AuthCard from './components/AuthCard.vue'
import ChatApp from './components/ChatApp.vue'
import { ApiError, clearToken, getToken, me, type User } from './auth'

const user = ref<User | null>(null)
const ready = ref(!getToken())
const main = ref<HTMLElement>()
const initials = computed(() =>
  (user.value?.display_name ?? '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w.charAt(0).toUpperCase()).join(''),
)

if (!ready.value) {
  me()
    .then((u) => (user.value = u))
    .catch((e) => e instanceof ApiError && e.status === 401 && clearToken())
    .finally(() => (ready.value = true))
}

function logout() {
  clearToken()
  user.value = null
}

function signOut() {
  history.replaceState(null, '', location.pathname + location.search)
  logout()
}

// The screen swaps under the user, so move focus to the new content.
watch(user, () => nextTick(() => main.value?.focus()))
</script>

<template>
  <a class="skip" href="#inhalt">Zum Inhalt springen</a>
  <header class="top">
    <div class="wrap">
      <span class="brand">
        <span class="brand-mark"><svg class="i" aria-hidden="true"><use href="#i-route" /></svg></span>
        <span :class="{ bl: user }"><b>SV KI-Lotse</b><small>Ihr Wegweiser durch die Sozialversicherung</small></span>
      </span>
      <span v-if="user" class="me">
        <a class="btn btn-quiet bar-list" href="#gespraeche" title="Alle Gespräche">
          <svg class="i" aria-hidden="true"><use href="#i-list" /></svg><span class="xs">Alle Gespräche</span>
        </a>
        <a class="btn btn-quiet me-btn" href="#einstellungen" title="Einstellungen">
          <span class="avatar" aria-hidden="true">{{ initials }}</span>
          <span class="bl me-l"><b>{{ user.display_name }}</b><small>Einstellungen</small></span>
        </a>
        <button type="button" class="btn btn-quiet" title="Abmelden" @click="signOut">
          <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg><span class="bl">Abmelden</span>
        </button>
      </span>
    </div>
  </header>

  <main id="inhalt" ref="main" :class="user ? 'signed-in' : 'wrap login'" tabindex="-1">
    <template v-if="ready">
      <ChatApp v-if="user" :user="user" @expired="logout" @deleted="signOut" />
      <AuthCard v-else @done="user = $event" />
    </template>
  </main>
</template>

<style scoped>
.top { background: var(--sheet); box-shadow: 0 1px 0 var(--rule); }
.top .wrap { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .75rem 1rem; padding-block: .6rem; }
.brand { display: flex; align-items: center; gap: .65rem; }
.brand-mark { width: 2.5rem; height: 2.5rem; flex: none; border-radius: 12px; background: var(--harbor); color: var(--on-harbor); display: grid; place-items: center; }
.brand-mark .i { width: 1.5rem; height: 1.5rem; }
.brand b { display: block; font-size: 1.15rem; line-height: 1.2; }
.brand small { display: block; font-size: .875rem; color: var(--ink-3); line-height: 1.3; }
.me { display: inline-flex; flex-wrap: wrap; align-items: center; gap: .25rem .75rem; }
.me-btn { padding-inline: .4rem .7rem; }
.avatar { width: 2.25rem; height: 2.25rem; flex: none; border-radius: 50%; background: var(--harbor-tint); color: var(--harbor); display: grid; place-items: center; font-weight: 700; font-size: .8rem; }
.me-l b { display: block; color: var(--ink); }
.me-l small { display: block; font-size: .8rem; font-weight: 600; }
main { display: grid; min-height: 0; overflow-y: auto; }
.login { padding-block: clamp(1.25rem, 4vh, 2.5rem); }
.signed-in { grid-template-rows: minmax(0, 1fr); }
@container (min-width: 56rem) { .bar-list { display: none; } }
/* Narrow, signed in: one bar row, labels stay for screen readers (as in the demo). */
@container (max-width: 55.99rem) {
  .bl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .me-btn { width: 2.75rem; padding: 0; }
}
/* Phone with large text: the list link shows only its icon, so the bar still fits one row. */
@container (max-width: 23.99rem) {
  .xs { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .me { gap: .25rem; }
}
</style>
