// Pure helpers for the settings form. No imports, so `npm test` can run them in plain node.

// Same check as backend/schemas.py: the 4th digit is the check digit, so its own weight is 0.
const WEIGHTS = [3, 7, 9, 0, 5, 8, 4, 2, 1, 6]
export const svnrDigits = (v: string) => v.replace(/\s/g, '')
export function svnrOk(v: string) {
  const d = svnrDigits(v)
  // A sum of 10 (mod 11) matches no digit, so such numbers are invalid.
  return /^\d{10}$/.test(d) && [...d].reduce((sum, c, i) => sum + Number(c) * WEIGHTS[i]!, 0) % 11 === Number(d[3])
}
/** "1237010180" -> "1237 010180", also while typing. */
export const fmtSvnr = (d: string) => d.replace(/^(\d{4})(?=\d)/, '$1 ')

/** "TT.MM.JJJJ" as far as typed. A single digit before a dot gets its 0: "1.1.1980" -> "01.01.1980". */
export function fmtDate(v: string) {
  const d = v.replace(/(^|\D)(\d)(?=\D)/g, '$10$2').replace(/\D/g, '').slice(0, 8)
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join('.')
}

/** A complete "TT.MM.JJJJ" that exists and is not in the future. */
export function realDate(v: string) {
  const [, d, m, y] = (/^(\d\d)\.(\d\d)\.(\d{4})$/.exec(v) ?? []).map(Number)
  const date = new Date(y!, m! - 1, d)
  return !!y && y >= 1900 && date.getMonth() === m! - 1 && date.getDate() === d && date <= new Date()
}

/** An SVNR is NNNC DDMMYY: the 4 digits from the e-card, then (usually) the birth date. null if the date part is no real date. */
export function splitSvnr(svnr: string, thisYear = new Date().getFullYear()) {
  const [, serial, dd, mm, yy] = /^(\d{4})(\d\d)(\d\d)(\d\d)$/.exec(svnr) ?? []
  if (!serial) return null
  // shortcut: years up to this year's two digits count as 20xx, so people over 100 see the wrong century; the SVNR only uses the last two digits.
  const birth = `${dd}.${mm}.${Number(yy) <= thisYear % 100 ? 20 : 19}${yy}`
  return realDate(birth) ? { serial, birth } : null
}

/** The 10-digit SVNR from the 4 e-card digits and the birth date, "" while either is incomplete. */
export function joinSvnr(serial: string, birth: string) {
  const m = /^(\d\d)\.(\d\d)\.\d\d(\d\d)$/.exec(birth)
  return m && /^\d{4}$/.test(serial) ? serial + m[1] + m[2] + m[3] : ''
}

/** As typed, in the international form: "0660 1234567" -> "+43 660 1234567". Vienna (1) and mobile (6xx) area codes get a space. */
export function fmtPhone(v: string) {
  const d = v.replace(/[^\d+]/g, '').replace(/(?!^)\+/g, '').replace(/^00/, '+').replace(/^0(?=\d)/, '+43')
  const m = /^\+43(1|6\d\d)?(\d*)$/.exec(d)
  return m ? ['+43', m[1], m[2]].filter(Boolean).join(' ') : d
}

/** Vienna's postal codes, 1010 to 1230 (as VIENNA_POSTAL_CODE in backend/facts.py). */
export const VIENNA = /^1(0[1-9]|1\d|2[0-3])0$/
