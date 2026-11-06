import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { WizardQuestion, WizardSection } from '../chats.ts'
import { check, EMPTY, paperDate, problem, shownIds, wire } from '../wizard.ts'

const q = (id: string, more: Partial<WizardQuestion> = {}): WizardQuestion => ({
  id, label: id, kind: 'text', options: {}, help: null, source_url: null, required: false, suggest: false, max: null,
  detail: null, when: [], value: '', source: null, source_label: null, ...more,
})
const section = (...questions: WizardQuestion[]): WizardSection => ({ id: 's', title: 's', heading: null, page: 1, point: 1, questions })

test('conditions are checked like the backend: any false decides, unknown is null', () => {
  assert.equal(check({ a: ['yes'] }, { a: 'yes' }), true)
  assert.equal(check({ a: ['yes'] }, { a: 'no' }), false)
  assert.equal(check({ a: ['yes'] }, {}), null)
  assert.equal(check({ a: { not: ['self'] } }, { a: 'mother' }), true)
  assert.equal(check({ a: ['x'], b: ['y'] }, { b: 'z' }), false)
  assert.equal(check({ goal: ['care'] }, { goal: ['care', 'money'] }), true) // a fact with several values
})

test('a question shows once an earlier answer allows it; a list of conditions means any of them', () => {
  const sections = [section(
    q('helps', { kind: 'yes_no' }),
    q('who', { when: [{ helps: ['yes'] }] }),
    q('empty', { when: [{ who: [EMPTY] }] }),
    q('either', { when: [{ helps: ['yes'] }, { who: ['x'] }] }),
  )]

  assert.deepEqual([...shownIds(sections, {}, {})], ['helps'])
  assert.deepEqual([...shownIds(sections, {}, { helps: 'yes' })], ['helps', 'who', 'empty', 'either'])
  assert.deepEqual([...shownIds(sections, {}, { helps: 'yes', who: 'x' })], ['helps', 'who', 'either'])
  assert.deepEqual([...shownIds(sections, {}, { helps: 'no', who: 'x' })], ['helps']) // hidden answers do not count
})

test('answers are checked as on the server', () => {
  assert.equal(problem(q('d', { kind: 'date' }), '31.12.2030'), '') // a leave may end in the future
  assert.equal(problem(q('d', { kind: 'date' }), '31.02.2024'), 'date')
  assert.equal(problem(q('b', { kind: 'date', detail: 'birth_date' }), '01.01.2999'), 'birth')
  assert.equal(problem(q('s', { detail: 'svnr' }), '1237 010180'), '')
  assert.equal(problem(q('s', { detail: 'svnr' }), '1234 567890'), 'svnr')
  assert.equal(problem(q('s', { detail: 'svnr', max: 10 }), '1237 010180'), '') // the space is not sent
  assert.equal(problem(q('p', { detail: 'postal_code' }), '110'), 'postal')
  assert.equal(problem(q('e', { detail: 'email' }), 'anna@'), 'email')
  assert.equal(problem(q('t', { max: 5 }), 'zu lang'), 'long')
  assert.equal(problem(q('t', { max: 5 }), ''), '')
  assert.equal(wire(q('s', { detail: 'svnr' }), '1237 010180'), '1237010180')
  assert.ok(paperDate('29.02.2024') && !paperDate('29.02.2023'))
})
