import test from 'node:test'
import assert from 'node:assert/strict'
import { searchStaticPapers, searchStaticEvents } from '../src/staticSearch.js'

const base = { _group: 0, year: 2025, title: 'One paper', acronym: 'SIGIR', category: 'paper', category_label: '最佳论文奖', award_name: 'Best Paper', status: 'verified', sources: [], authors: [], _duplicate_key: 'same-paper-award' }
const rows = [
  { ...base, id: 'record', _legacy: true, award_type: 'best_paper', authors: [{ name: 'Alice', affiliations: [{ name: 'University A' }] }, { name: 'Bob', affiliations: [{ name: 'University B' }] }], date_start: '2025-01-01', date_end: '2025-12-31' },
  { ...base, id: 'event', _legacy: false, source_kind: 'award_event', authors_raw: 'Alice; Charlie' },
  { ...base, id: 'student', _legacy: false, source_kind: 'award_event', category: 'student', category_label: '最佳学生论文奖', award_name: 'Best Student Paper', _duplicate_key: 'same-paper-student-award', authors_raw: 'Alice; Charlie' },
]

test('one paper retains all awards while duplicate source records are suppressed', () => {
  const result = searchStaticPapers(rows)
  assert.equal(result.total, 1)
  assert.deepEqual(result.records[0].related_record_ids, ['record', 'student'])
  assert.deepEqual(result.records[0].categories, ['paper', 'student'])
})

test('author and category filtering precede merging and source suppression', () => {
  const result = searchStaticPapers(rows, { author: 'Charlie', category: 'paper' })
  assert.equal(result.records[0].id, 'event')
  assert.equal(searchStaticPapers(rows, { category: 'student' }).records[0].award_name, 'Best Student Paper')
})

test('author and affiliation must describe the same person, and unknown dates never match', () => {
  assert.equal(searchStaticPapers(rows, { author: 'Alice', affiliation: 'University B' }).total, 0)
  assert.equal(searchStaticPapers(rows, { author: 'Alice', affiliation: 'University A' }).total, 1)
  assert.deepEqual(searchStaticPapers(rows, { published_from: '2025-06-01' }).records[0].related_record_ids, ['record'])
  assert.equal(searchStaticPapers(rows, { published_from: '2026-01-01' }).total, 0)
})

test('annual awards search includes paper titles and paginates after filtering', () => {
  const events = [0, 1, 2].map(i => ({ id: i, venue: 'SIGIR', category: 'paper', _query: ['best paper', `learning ${i}`] }))
  assert.deepEqual(searchStaticEvents(events, { query: 'Learning', offset: 1, limit: 1 }), { total: 3, events: [events[1]] })
  assert.equal(searchStaticEvents(events, { query: 'unavailable' }).total, 0)
})
