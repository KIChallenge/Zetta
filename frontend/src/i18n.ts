import { computed, ref, shallowRef } from 'vue'

// German is the source everywhere, also in what the backend sends. t() looks a text up in the catalog of the chosen
// language and falls back to the German text. The catalogs are built by backend/scripts/translate.py.
const CATALOGS = import.meta.glob<{ default: Record<string, string> }>('./locales/*.json')
const KEY = 'lotse-sprache'

export const locale = ref('de')
const catalog = shallowRef<Record<string, string>>({})
/** Whether the interface is shown in another language than German. */
export const translating = computed(() => Object.keys(catalog.value).length > 0)
/** For dates and times: only the languages the interface is actually shown in. */
export const intlLocale = computed(() => (translating.value ? locale.value : 'de-AT'))

/** Marks a text for translation without translating it yet, e.g. in a constant. Show it with t(). */
export const k = (text: string) => text

// Texts with a variable part, as the backend builds them. Each named group is translated if it can be.
const PATTERNS: [RegExp, string][] = [
  [/^(?<n>\d+) offene Schritte$/, k('{n} offene Schritte')],
  [/^Jetzt erreichbar bis (?<time>[\d:]+) Uhr$/, k('Jetzt erreichbar bis {time} Uhr')],
  [/^Erreichbar heute ab (?<time>[\d:]+) Uhr$/, k('Erreichbar heute ab {time} Uhr')],
  [/^Erreichbar morgen ab (?<time>[\d:]+) Uhr$/, k('Erreichbar morgen ab {time} Uhr')],
  [/^Erreichbar (?<day>Mo|Di|Mi|Do|Fr|Sa|So) ab (?<time>[\d:]+) Uhr$/, k('Erreichbar {day} ab {time} Uhr')],
  [/^Voraussetzung nicht erfüllt: (?<reason>.+)$/, k('Voraussetzung nicht erfüllt: {reason}')],
  [/^Gibt es nur (?<season>.+)\.$/, k('Gibt es nur {season}.')],
  [/^Kassen: (?<insurers>.+)$/, k('Kassen: {insurers}')],
  [/^Vertrag nur mit: (?<insurers>.+)\. Bei einer anderen Kasse zahlen Sie die Behandlung zuerst selbst\.$/, k('Vertrag nur mit: {insurers}. Bei einer anderen Kasse zahlen Sie die Behandlung zuerst selbst.')],
  [/^Wenden Sie sich an: (?<name>.+)\. Die Kontaktdaten sind im Lotsen noch nicht hinterlegt\.$/, k('Wenden Sie sich an: {name}. Die Kontaktdaten sind im Lotsen noch nicht hinterlegt.')],
]
k('Jetzt erreichbar, rund um die Uhr')

const fill = (text: string, vars: Record<string, string | number>) =>
  text.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? String(vars[name]) : m))

function dynamic(text: string): string {
  const c = catalog.value
  for (const [re, key] of PATTERNS) {
    const groups = re.exec(text)?.groups
    if (!groups) continue
    const vars = Object.fromEntries(
      Object.entries(groups).map(([name, v]) => [name, name === 'day' ? weekday(v) : t(v)]),
    )
    return fill(c[key] ?? key, vars)
  }
  // A fact edit as stored in the chat ("Bezirk: 10., Favoriten") or several picked chips ("Entlassung, Besuch").
  const colon = text.indexOf(': ')
  if (colon > 0 && c[text.slice(0, colon)]) return `${c[text.slice(0, colon)]}: ${t(text.slice(colon + 2))}`
  const parts = text.split(', ')
  if (parts.length > 1 && parts.every((p) => c[p])) return parts.map((p) => c[p]).join(', ')
  return text
}

export function t(text: string, vars?: Record<string, string | number>): string {
  const c = catalog.value
  if (!translating.value) return vars ? fill(text, vars) : text
  const found = c[text]
  if (vars) return fill(found ?? text, vars)
  return found ?? dynamic(text)
}

const DAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
function weekday(day: string) {
  // 1 January 2024 was a Monday.
  const date = new Date(2024, 0, 1 + DAYS.indexOf(day))
  return new Intl.DateTimeFormat(intlLocale.value, { weekday: 'short' }).format(date)
}

/** Opening hours as the backend writes them, e.g. "Mo–Mi 8:00–12:00, täglich 8:00–20:00". */
export function hours(text: string): string {
  if (!translating.value) return text
  return text
    .replace(/\b(Mo|Di|Mi|Do|Fr|Sa|So)\b/g, weekday)
    .replace('täglich', t('täglich'))
    .replace('rund um die Uhr', t('rund um die Uhr'))
}

export async function setLocale(code: string) {
  const load = CATALOGS[`./locales/${code}.json`]
  catalog.value = load ? (await load()).default : {}
  locale.value = code
  document.documentElement.lang = load ? code : 'de-AT'
  try {
    localStorage.setItem(KEY, code)
  } catch {
    // Private mode or storage blocked: the language still applies until reload.
  }
}

/** The language chosen on this device, else the browser's if we have it, else German. */
export function initialLocale() {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(KEY)
  } catch {
    // As above.
  }
  const browser = navigator.language.slice(0, 2)
  return stored ?? (CATALOGS[`./locales/${browser}.json`] ? browser : 'de')
}

// Someone who registers keeps the language they picked on the login screen. On a later login the profile decides.
let registering = false
export const markRegistering = () => (registering = true)
export function takeRegistering() {
  const was = registering
  registering = false
  return was
}
