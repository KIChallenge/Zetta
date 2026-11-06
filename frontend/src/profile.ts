import { api, type Entry } from './chats'
import { fmtSvnr } from './fields'
import { k } from './i18n'

export const LANGS = {
  de: 'Deutsch', en: 'English', fr: 'Français', cs: 'Čeština', sk: 'Slovenčina', sl: 'Slovenščina', tr: 'Türkçe', bks: 'Bosanski / Hrvatski / Srpski', ro: 'Română',
  pl: 'Polski', hu: 'Magyar', uk: 'Українська', ar: 'العربية',
} as const
export const LENGTHS = { short: k('Kurz und knapp'), detailed: k('Ausführlich erklärt') } as const

/** Everything is optional: personal fields are "" when unset. */
export interface Profile {
  full_name: string
  street: string
  postal_code: string
  city: string
  svnr: string
  phone: string
  contact_email: string
  answer_language: keyof typeof LANGS
  answer_length: keyof typeof LENGTHS
  phone_calls: boolean // false: calls become emails where Zetta has an address
}

export const getProfile = () => api<Profile>('/me/profile')
export const saveProfile = (p: Profile) => api<Profile>('/me/profile', 'PUT', p)
/** A person details can be kept for ("self": the user's own ones beyond the profile), from form cards or the settings. */
export interface KeptPerson {
  relation: string
  label: string
  kept: boolean
  entries: (Entry & { shown: string })[]
}
export const getPeople = () => api<KeptPerson[]>('/me/people')
export const savePerson = (relation: string, details: Record<string, string>) =>
  api<KeptPerson>(`/me/people/${encodeURIComponent(relation)}`, 'PUT', details)
export const deletePerson = (relation: string) => api<null>(`/me/people/${encodeURIComponent(relation)}`, 'DELETE')
export const changePassword = (current_password: string, new_password: string) =>
  api<null>('/me/password', 'POST', { current_password, new_password })
export const deleteAccount = (password: string) => api<null>('/me', 'DELETE', { password })

/** Every field as a label/value pair, "" when unset: what Zetta fills into call scripts and emails (never sent to the LLM). */
export function facts(p: Profile): [string, string][] {
  const place = `${p.postal_code} ${p.city}`.trim()
  return [
    [k('Name'), p.full_name],
    [k('Adresse'), [p.street, place].filter(Boolean).join(', ')],
    [k('SV-Nummer'), fmtSvnr(p.svnr)],
    [k('Telefon'), p.phone],
    [k('E-Mail'), p.contact_email],
  ]
}
