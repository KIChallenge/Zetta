<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import AuthCard from './components/AuthCard.vue'
import ChatApp from './components/ChatApp.vue'
import { ApiError, clearToken, getToken, me, type User } from './auth'

const user = ref<User | null>(null)
const ready = ref(!getToken())
const main = ref<HTMLElement>()

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
        <a class="btn btn-quiet bar-list" href="#gespraeche">
          <svg class="i" aria-hidden="true"><use href="#i-list" /></svg>Alle Gespräche
        </a>
        <b class="bl">{{ user.display_name }}</b>
        <button type="button" class="btn btn-quiet" title="Abmelden" @click="signOut">
          <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg><span class="bl">Abmelden</span>
        </button>
      </span>
    </div>
  </header>

  <main id="inhalt" ref="main" :class="user ? 'signed-in' : 'wrap login'" tabindex="-1">
    <template v-if="ready">
      <ChatApp v-if="user" :user="user" @expired="logout" />
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
main { display: grid; min-height: 0; overflow-y: auto; }
.login { padding-block: clamp(1.25rem, 4vh, 2.5rem); }
.signed-in { grid-template-rows: minmax(0, 1fr); }
@media (min-width: 56rem) { .bar-list { display: none; } }
/* Narrow, signed in: one bar row, labels stay for screen readers (as in the demo). */
@media (max-width: 55.99rem) { .bl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; } }
</style>
