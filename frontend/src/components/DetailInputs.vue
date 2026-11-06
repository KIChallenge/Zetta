<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { Entry } from '../chats'
import { fmtDate, fmtPhone, realDate, svnrDigits, svnrOk, VIENNA } from '../fields'
import { k, t } from '../i18n'

// Inputs for a person's details, as a form card and the settings page ask for them. `scope` tells the people apart
// ("user", "subject", "mother"); an entry's own `who` wins over it.
const props = defineProps<{ entries: Entry[]; scope: string; own: boolean }>()

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/ // as in AuthCard
const INPUTS: Record<string, { label: string; max: number; type?: string; mode?: 'numeric'; hint?: string }> = {
  full_name: { label: k('Vor- und Nachname'), max: 100 },
  street: { label: k('Straße und Hausnummer'), max: 100, hint: k('Mit Stiege und Tür, zum Beispiel Favoritenstraße 12/3/4') },
  postal_code: { label: k('PLZ'), max: 4, mode: 'numeric' },
  city: { label: k('Ort'), max: 60 },
  svnr: { label: k('Sozialversicherungsnummer'), max: 11, mode: 'numeric', hint: k('10 Ziffern, wie auf der e-card') },
  phone: { label: k('Telefonnummer'), max: 30, type: 'tel' },
  contact_email: { label: k('E-Mail-Adresse'), max: 254, type: 'email' },
  title: { label: k('Titel'), max: 30, hint: k('Zum Beispiel Mag. oder Dr.') },
  birth_date: { label: k('Geburtsdatum'), max: 10, mode: 'numeric', hint: k('TT.MM.JJJJ') },
}
// The browser may fill in the user's own details, never someone else's.
const AUTO: Record<string, string> = {
  full_name: 'name', street: 'street-address', postal_code: 'postal-code', city: 'address-level2', phone: 'tel',
  contact_email: 'email', title: 'honorific-prefix', birth_date: 'bday',
}

const who = (e: Entry) => e.who ?? props.scope
const key = (e: Entry, f: string) => `${who(e)}.${f}`
const vals = reactive<Record<string, string>>({})
const errors = reactive<Record<string, string>>({})

// What is known already (e.g. the city of an address) starts filled in; the date is shown as on paper. Entries
// shown later (more of them) start so too, without touching what was typed meanwhile.
watch(
  () => props.entries,
  (entries) => {
    for (const e of entries)
      for (const f of e.fields)
        if (!(key(e, f) in vals)) vals[key(e, f)] = f === 'birth_date' ? toPaper(e.values[f] ?? '') : (e.values[f] ?? '')
  },
  { immediate: true },
)

function toPaper(iso: string) {
  const [y, m, d] = iso.split('-')
  return iso ? `${d}.${m}.${y}` : ''
}
function toIso(paper: string) {
  const [d, m, y] = paper.split('.')
  return `${y}-${m}-${d}`
}

function rule(f: string, v: string) {
  if (!v) return ''
  if (f === 'postal_code' && !/^\d{4}$/.test(v)) return t('Die Postleitzahl hat 4 Ziffern, zum Beispiel 1100.')
  if (f === 'contact_email' && !EMAIL.test(v)) return t('Bitte prüfen Sie die E-Mail-Adresse. Sie sieht so aus: name@beispiel.at')
  if (f === 'birth_date' && !realDate(v)) return t('Bitte prüfen Sie das Geburtsdatum.')
  if (f === 'svnr' && !svnrOk(v)) return t('Diese Nummer gibt es nicht. Bitte vergleichen Sie die Ziffern mit Ihrer e-card.')
  return ''
}

function onInput(e: Entry, f: string) {
  const id = key(e, f)
  if (f === 'birth_date') vals[id] = fmtDate(vals[id]!)
  if (f === 'phone') vals[id] = fmtPhone(vals[id]!)
  if (f === 'postal_code') {
    vals[id] = vals[id]!.replace(/\D/g, '')
    const city = key(e, 'city')
    if (VIENNA.test(vals[id]!) && city in vals && !vals[city]!.trim()) vals[city] = 'Wien'
  }
  if (errors[id]) errors[id] = rule(f, vals[id]!.trim())
}

function pick(e: Entry, f: string, value: string) {
  const id = key(e, f)
  vals[id] = vals[id] === value ? '' : value
}

/** Person -> field -> value, empty ones included. null, and the first wrong input focused, if one is invalid. */
function collect(): Record<string, Record<string, string>> | null {
  const out: Record<string, Record<string, string>> = {}
  let first = ''
  for (const e of props.entries)
    for (const f of e.fields) {
      const id = key(e, f)
      const v = vals[id]!.trim()
      errors[id] = e.choices[f] ? '' : rule(f, v)
      if (errors[id]) first ||= id
      ;(out[who(e)] ??= {})[f] = f === 'birth_date' && v ? toIso(v) : f === 'svnr' ? svnrDigits(v) : v
    }
  if (first) {
    document.getElementById(`di-${first}`)?.focus()
    return null
  }
  return out
}
defineExpose({ collect })
</script>

<template>
  <fieldset v-for="e in entries" :key="`${who(e)}.${e.entry}`" class="di-entry">
    <legend class="field-l">{{ t(e.label) }}</legend>
    <template v-for="f in e.fields" :key="f">
      <div v-if="e.choices[f]" class="chips">
        <button
          v-for="(label, value) in e.choices[f]"
          :key="value"
          type="button"
          class="chip"
          :aria-pressed="vals[key(e, f)] === value"
          @click="pick(e, f, String(value))"
        >{{ t(label) }}</button>
      </div>
      <div v-else class="field">
        <label v-if="e.fields.length > 1" class="sub-l" :for="`di-${key(e, f)}`">{{ t(INPUTS[f]!.label) }}</label>
        <input
          :id="`di-${key(e, f)}`"
          v-model="vals[key(e, f)]"
          class="input"
          :type="INPUTS[f]!.type ?? 'text'"
          :inputmode="INPUTS[f]!.mode"
          :maxlength="INPUTS[f]!.max"
          :autocomplete="own && (who(e) === 'user' || who(e) === 'self') ? AUTO[f] ?? 'off' : 'off'"
          :aria-label="e.fields.length > 1 ? undefined : t(e.label)"
          :aria-invalid="!!errors[key(e, f)]"
          :aria-describedby="`di-${key(e, f)}-d`"
          @input="onInput(e, f)"
          @blur="vals[key(e, f)]?.trim() && (errors[key(e, f)] = rule(f, vals[key(e, f)]!.trim()))"
        />
        <p :id="`di-${key(e, f)}-d`" :class="errors[key(e, f)] ? 'err' : 'hint'">
          <template v-if="errors[key(e, f)]"><svg class="i" aria-hidden="true"><use href="#i-alert" /></svg><span>{{ errors[key(e, f)] }}</span></template>
          <template v-else-if="INPUTS[f]!.hint">{{ t(INPUTS[f]!.hint!) }}</template>
        </p>
      </div>
    </template>
  </fieldset>
</template>

<style scoped>
.di-entry { margin: 0; padding: 0; border: 0; display: grid; gap: .5rem; }
.sub-l { font-size: var(--fs-small); color: var(--ink-2); }
.field .hint, .field .err { margin: 0; }
</style>
