import { api } from './chats'
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
}

export const getProfile = () => api<Profile>('/me/profile')
export const saveProfile = (p: Profile) => api<Profile>('/me/profile', 'PUT', p)
export const changePassword = (current_password: string, new_password: string) =>
  api<null>('/me/password', 'POST', { current_password, new_password })
export const deleteAccount = (password: string) => api<null>('/me', 'DELETE', { password })

// Same check as backend/schemas.py: the 4th digit is the check digit, so its own weight is 0.
const WEIGHTS = [3, 7, 9, 0, 5, 8, 4, 2, 1, 6]
export const svnrDigits = (v: string) => v.replace(/\s/g, '')
export function svnrOk(v: string) {
  const d = svnrDigits(v)
  // A sum of 10 (mod 11) matches no digit, so such numbers are invalid.
  return /^\d{10}$/.test(d) && [...d].reduce((sum, c, i) => sum + Number(c) * WEIGHTS[i]!, 0) % 11 === Number(d[3])
}
export const fmtSvnr = (d: string) => (d.length === 10 ? `${d.slice(0, 4)} ${d.slice(4)}` : d)

/** The filled fields as label/value pairs: what the Lotse fills into call scripts and emails (never sent to the LLM). */
export function facts(p: Profile): [string, string][] {
  const place = `${p.postal_code} ${p.city}`.trim()
  const all: [string, string][] = [
    [k('Name'), p.full_name],
    [k('Adresse'), [p.street, place].filter(Boolean).join(', ')],
    [k('SV-Nummer'), fmtSvnr(p.svnr)],
    [k('Telefon'), p.phone],
    [k('E-Mail'), p.contact_email],
  ]
  return all.filter(([, v]) => v)
}
