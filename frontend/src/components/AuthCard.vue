<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import { ApiError, authenticate, type User } from '../auth'

type Mode = 'login' | 'register'
type Field = 'display_name' | 'email' | 'password'

const emit = defineEmits<{ done: [user: User] }>()

const TABS = [['login', 'Anmelden'], ['register', 'Neu registrieren']] as const
const MESSAGES: Record<string, string> = {
  'login 401': 'E-Mail-Adresse oder Passwort stimmt nicht.',
  'register 409': 'Mit dieser E-Mail-Adresse gibt es schon ein Konto. Bitte melden Sie sich an.',
}
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const mode = ref<Mode>('login')
const form = reactive({ display_name: '', email: '', password: '' })
const errors = reactive({ display_name: '', email: '', password: '' })
const formError = ref('')
const busy = ref(false)
const showPw = ref(false)

const rules: Record<Field, (v: string) => string> = {
  display_name: (v) => (v.trim() ? '' : 'Bitte sagen Sie uns, wie wir Sie nennen dürfen.'),
  email: (v) =>
    !v.trim() ? 'Bitte geben Sie Ihre E-Mail-Adresse ein.'
    : !EMAIL.test(v.trim()) ? 'Bitte prüfen Sie die E-Mail-Adresse. Sie sieht so aus: name@beispiel.at'
    : '',
  password: (v) =>
    mode.value === 'register'
      ? v.length < 10 ? 'Das Passwort braucht mindestens 10 Zeichen.' : ''
      : v ? '' : 'Bitte geben Sie Ihr Passwort ein.',
}
const check = (f: Field) => !(errors[f] = rules[f](form[f]))
// Live re-check only once a field has been flagged, as in the demo.
const recheck = (f: Field) => errors[f] && check(f)

function select(m: Mode, focus = false) {
  mode.value = m
  Object.assign(errors, { display_name: '', email: '', password: '' })
  formError.value = ''
  if (focus) nextTick(() => document.getElementById(`t-${m}`)?.focus())
}

function onTabKey(e: KeyboardEvent) {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  e.preventDefault()
  select(mode.value === 'login' ? 'register' : 'login', true)
}

async function submit() {
  if (busy.value) return
  formError.value = ''
  const fields: Field[] = mode.value === 'register' ? ['display_name', 'email', 'password'] : ['email', 'password']
  const bad = fields.filter((f) => !check(f))
  if (bad.length) {
    document.getElementById(`f-${bad[0]}`)?.focus()
    return
  }
  busy.value = true
  try {
    const creds = { email: form.email.trim(), password: form.password }
    emit(
      'done',
      mode.value === 'login'
        ? await authenticate('/auth/login', creds)
        : await authenticate('/auth/register', { ...creds, display_name: form.display_name.trim() }),
    )
  } catch (e) {
    formError.value = (e instanceof ApiError && MESSAGES[`${mode.value} ${e.status}`]) || (e as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="auth" aria-label="Anmelden oder registrieren">
    <div class="tabs" role="tablist" aria-label="Anmelden oder registrieren">
      <button
        v-for="[t, label] in TABS"
        :id="`t-${t}`"
        :key="t"
        type="button"
        class="tab"
        role="tab"
        aria-controls="auth-panel"
        :aria-selected="mode === t"
        :tabindex="mode === t ? 0 : -1"
        @click="select(t)"
        @keydown="onTabKey"
      >
        {{ label }}
      </button>
    </div>

    <div id="auth-panel" role="tabpanel" :aria-labelledby="`t-${mode}`">
      <form novalidate @submit.prevent="submit">
        <h2 class="sr">{{ mode === 'login' ? 'Anmelden' : 'Neu registrieren' }}</h2>
        <p v-if="formError" class="form-err" role="alert">
          <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ formError }}</span>
        </p>

        <div v-if="mode === 'register'" class="field">
          <label class="field-l" for="f-display_name">Wie dürfen wir Sie nennen?</label>
          <input
            id="f-display_name"
            v-model="form.display_name"
            class="input"
            autocomplete="name"
            :aria-invalid="!!errors.display_name"
            aria-describedby="f-display_name-err"
            @input="recheck('display_name')"
          />
          <p v-if="errors.display_name" id="f-display_name-err" class="err">
            <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors.display_name }}</span>
          </p>
        </div>

        <div class="field">
          <label class="field-l" for="f-email">E-Mail-Adresse</label>
          <input
            id="f-email"
            v-model="form.email"
            class="input"
            type="email"
            autocomplete="email"
            :aria-invalid="!!errors.email"
            aria-describedby="f-email-err"
            @input="recheck('email')"
          />
          <p v-if="errors.email" id="f-email-err" class="err">
            <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors.email }}</span>
          </p>
        </div>

        <div class="field">
          <label class="field-l" for="f-password">Passwort</label>
          <div class="pw">
            <input
              id="f-password"
              v-model="form.password"
              class="input"
              :type="showPw ? 'text' : 'password'"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              :aria-invalid="!!errors.password"
              :aria-describedby="mode === 'register' ? 'f-password-rule f-password-err' : 'f-password-err'"
              @input="recheck('password')"
            />
            <button type="button" class="btn btn-quiet" aria-controls="f-password" :aria-pressed="showPw" @click="showPw = !showPw">
              <svg class="i" aria-hidden="true"><use href="#i-eye" /></svg>Anzeigen
            </button>
          </div>
          <p v-if="mode === 'register'" id="f-password-rule" class="hint pw-rule" :class="{ ok: form.password.length >= 10 }">
            <svg class="i" aria-hidden="true"><use href="#i-check" /></svg>Mindestens 10 Zeichen
          </p>
          <p v-if="errors.password" id="f-password-err" class="err">
            <svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors.password }}</span>
          </p>
        </div>

        <button type="submit" class="btn btn-primary btn-block" :aria-disabled="busy">
          {{ busy ? 'Einen Moment …' : mode === 'login' ? 'Anmelden' : 'Konto erstellen' }}
        </button>
      </form>
    </div>
  </section>
</template>

<style scoped>
.auth { width: min(100%, 26rem); padding: clamp(1.1rem, 3vw, 1.75rem); border: var(--hair); border-radius: var(--r-l); background: var(--sheet); }
/* Tabs: an underline marks the open one. */
.tabs { display: grid; grid-template-columns: 1fr 1fr; margin-bottom: 1.5rem; border-bottom: var(--hair); }
.tab { min-height: 2.75rem; padding: .4rem .5rem; border: 0; border-bottom: 3px solid transparent; margin-bottom: -1px; background: transparent; font: inherit; font-weight: 600; color: var(--ink-2); cursor: pointer; transition: color .15s, border-color .15s; }
.tab:hover { color: var(--head); border-bottom-color: var(--rule-2); }
.tab[aria-selected="true"] { color: var(--head); font-weight: 700; border-bottom-color: var(--accent); }
.tab:focus-visible { outline-offset: -3px; border-radius: var(--r-s) var(--r-s) 0 0; }
form { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; }
.pw { display: flex; gap: .5rem; }
.pw .input { flex: 1; min-width: 0; }
.pw .btn { flex: none; }
.form-err { display: flex; gap: .55em; align-items: flex-start; padding: .75rem 1rem; border-radius: var(--r-m); background: color-mix(in srgb, var(--danger) 10%, var(--sheet)); color: var(--danger); font-weight: 600; }
.form-err .i { margin-top: .15em; }
.pw-rule { display: flex; gap: .4em; align-items: center; }
.pw-rule.ok { color: var(--ready-ink); }
.pw-rule .i { width: 1.05em; height: 1.05em; }
</style>
