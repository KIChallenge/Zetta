import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fmtDate, fmtPhone, fmtSvnr, joinSvnr, splitSvnr, svnrOk } from '../fields.ts'

test('an SVNR splits into the 4 e-card digits and the birth date, and joins back', () => {
  assert.deepEqual(splitSvnr('1237010180', 2026), { serial: '1237', birth: '01.01.1980' })
  assert.deepEqual(splitSvnr('1237010105', 2026), { serial: '1237', birth: '01.01.2005' })
  assert.equal(joinSvnr('1237', '01.01.1980'), '1237010180')
  assert.ok(svnrOk(joinSvnr('1237', '01.01.1980')))
  assert.ok(!svnrOk(joinSvnr('1238', '01.01.1980')))
})

test('nothing is composed while a part is missing, and odd date parts do not split', () => {
  assert.equal(joinSvnr('123', '01.01.1980'), '')
  assert.equal(joinSvnr('1237', '01.01.19'), '')
  assert.equal(splitSvnr('1237011380'), null) // month 13: entered as the whole number instead
  assert.equal(splitSvnr('123'), null)
})

test('inputs are formatted as typed', () => {
  assert.equal(fmtSvnr('1237010180'), '1237 010180')
  assert.equal(fmtSvnr('12370'), '1237 0')
  assert.equal(fmtDate('01011980'), '01.01.1980')
  assert.equal(fmtDate('1.1.1980'), '01.01.1980')
  assert.equal(fmtDate('010'), '01.0')
  assert.equal(fmtPhone('0660 1234567'), '+43 660 1234567')
  assert.equal(fmtPhone('01/5123456'), '+43 1 5123456')
  assert.equal(fmtPhone('+43 660 1234567'), '+43 660 1234567')
  assert.equal(fmtPhone('0049 30 123'), '+4930123')
})
