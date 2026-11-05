<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import AuthCard from './components/AuthCard.vue'
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

// The screen swaps under the user, so move focus to the new content.
watch(user, () => nextTick(() => main.value?.focus()))
</script>

<template>
  <a class="skip" href="#inhalt">Zum Inhalt springen</a>
  <header class="top">
    <div class="wrap">
      <span class="brand">
        <span class="brand-mark"><svg class="i" aria-hidden="true"><use href="#i-route" /></svg></span>
        <span><b>SV KI-Lotse</b><small>Ihr Wegweiser durch die Sozialversicherung</small></span>
      </span>
      <span v-if="user" class="me">
        <b>{{ user.display_name }}</b>
        <button type="button" class="btn btn-quiet" @click="logout">
          <svg class="i" aria-hidden="true"><use href="#i-logout" /></svg>Abmelden
        </button>
      </span>
    </div>
  </header>

  <main id="inhalt" ref="main" class="wrap" tabindex="-1">
    <template v-if="ready">
      <h1 v-if="user" class="hello">Guten Tag, {{ user.display_name }}.</h1>
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
main { display: grid; padding-block: clamp(1.25rem, 4vh, 2.5rem); }
.hello { font-size: clamp(1.75rem, 4vw, 2.4rem); letter-spacing: -.02em; }
</style>
