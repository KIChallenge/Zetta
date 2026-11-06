// Pure helpers for the form wizard. Only type imports and fields.ts, so `npm test` can run them in plain node.
import type { Condition, WizardQuestion, WizardSection } from './chats'
import { realDate, svnrOk, VIENNA } from './fields.ts'

/** An unanswered question, as the backend's conditions see it (forms.EMPTY). */
export const EMPTY = 'empty'
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/ // as in AuthCard

/** As engine.check: true or false, or null while a value it needs is unknown. Any false decides. */
export function check(condition: Condition, state: Record<string, string | string[]>): boolean | null {
  let result: boolean | null = true
  for (const [key, matcher] of Object.entries(condition)) {
    const raw = state[key]
    const values = raw === undefined || (Array.isArray(raw) && !raw.length) ? null : Array.isArray(raw) ? raw : [raw]
    if (!values) {
      result = null
      continue
    }
    const ok = Array.isArray(matcher) ? values.some((v) => matcher.includes(v)) : !values.some((v) => matcher.not.includes(v))
    if (!ok) return false
  }
  return result
}

/** The ids of the questions shown for these answers, as forms.rows decides it: in order, each looking back. */
export function shownIds(sections: WizardSection[], facts: Record<string, string | string[]>, values: Record<string, string>) {
  const state: Record<string, string | string[]> = { ...facts }
  const shown = new Set<string>()
  for (const q of sections.flatMap((s) => s.questions)) {
    if (q.when.length && !q.when.some((c) => check(c, state) === true)) continue
    shown.add(q.id)
    state[q.id] = values[q.id] || EMPTY
  }
  return shown
}

/** A question that depends on an earlier one (not only on chat facts): drawn as a branch of it. */
export const follows = (q: WizardQuestion, ids: Set<string>) => q.when.some((c) => Object.keys(c).some((key) => ids.has(key)))

/** "TT.MM.JJJJ" that exists, any year from 1900 to 2100 (a leave can end in the future). */
export function paperDate(v: string) {
  const [, d, m, y] = (/^(\d\d)\.(\d\d)\.(\d{4})$/.exec(v) ?? []).map(Number)
  const date = new Date(y!, m! - 1, d)
  return !!y && y >= 1900 && y <= 2100 && date.getMonth() === m! - 1 && date.getDate() === d
}

export type Problem = '' | 'date' | 'birth' | 'svnr' | 'postal' | 'email' | 'phone' | 'number' | 'long'

/** What is wrong with an answer, checked as forms.valid does; "" when nothing. Choices come from chips, always valid. */
export function problem(q: WizardQuestion, raw: string): Problem {
  const v = raw.trim()
  if (!v || ['choice', 'yes_no', 'checkbox'].includes(q.kind)) return ''
  if (q.detail === 'birth_date') return realDate(v) ? '' : 'birth'
  if (q.kind === 'date' && !paperDate(v)) return 'date'
  if (q.detail === 'svnr' && !svnrOk(v)) return 'svnr'
  if (q.detail === 'postal_code' && !/^\d{4}$/.test(v)) return 'postal'
  if (q.detail === 'email' && !EMAIL.test(v)) return 'email'
  if (q.detail === 'phone' && !/^[0-9 +()-]*$/.test(v)) return 'phone'
  if (q.kind === 'number' && !/^\d+$/.test(v)) return 'number'
  if (q.max !== null && wire(q, v).length > q.max) return 'long' // as sent: an SVNR without its space
  return ''
}

/** The answer as it is sent: trimmed, an SVNR without its space. */
export function wire(q: WizardQuestion, v: string) {
  return q.detail === 'svnr' ? v.replace(/\s/g, '') : v.trim()
}

/** A Vienna postal code fills in the city, if it is still empty. */
export const viennaCity = (postal: string, city: string) => (VIENNA.test(postal) && !city.trim() ? 'Wien' : city)
