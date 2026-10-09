import test from 'node:test'
import assert from 'node:assert/strict'
import { authorText, affiliationText, paperLink, overviewRows, overviewStats, overviewCsv } from '../src/paperOverview.js'

const rows = [
  { id: 'a', acronym: 'AAAI', year: 2026, title: 'Learning Memory', rank: 'A', category: 'paper', award_name: 'Outstanding Paper', status: 'verified', authors: [{ name: 'An Author', affiliations: [{ name: 'HNUST' }] }], sources: [{ url: 'https://example.com/award' }] },
  { id: 'b', acronym: 'AAAI', year: 2026, title: 'Learning Memory', rank: 'A', category: 'student', award_name: 'Best Student Paper', status: 'verified', authors_raw: 'Another Author' },
  { id: 'c', acronym: 'ACL', year: 2025, title: 'Language Paper', rank: 'A', category: 'paper', status: 'pending' },
  { id: 'd', acronym: 'BIBM', year: 2024, title: 'Bio Paper', rank: 'B', category: 'paper', status: 'rejected' },
]

test('multi-conference, year, category and review filters compose without changing input', () => {
  const before = JSON.stringify(rows)
  assert.deepEqual(overviewRows(rows, { conferences: ['aaai', 'acl'], year_from: 2025, category: 'paper', status: 'verified' }).map(r => r.id), ['a'])
  assert.equal(overviewRows(rows, { status: 'all' }).length, 4)
  assert.equal(overviewRows(rows, { status: 'active' }).length, 3)
  assert.equal(overviewRows(rows, { rank: 'B' }).length, 1)
  assert.equal(JSON.stringify(rows), before)
})

test('keywords match case-insensitively across title, authors, units and original awards', () => {
  assert.deepEqual(overviewRows(rows, { query: 'MEMORY hnust outstanding' }).map(r => r.id), ['a'])
  assert.deepEqual(overviewRows(rows, { query: 'another STUDENT' }).map(r => r.id), ['b'])
  assert.equal(overviewRows(rows, { query: 'not present' }).length, 0)
})

test('sorting is deterministic and retains multiple awards for a paper', () => {
  assert.deepEqual(overviewRows([...rows].reverse()).map(r => r.id), ['b', 'a', 'c', 'd'])
  assert.deepEqual(overviewRows(rows, {}, 'title').map(r => r.id), ['d', 'c', 'b', 'a'])
  assert.deepEqual(overviewStats(rows), { records: 4, papers: 3, conferences: 3, yearFrom: 2024, yearTo: 2026 })
  assert.equal(overviewRows(rows, { year_from: 2026, year_to: 2025 }).length, 0)
  assert.deepEqual(overviewStats([]), { records: 0, papers: 0, conferences: 0, yearFrom: null, yearTo: null })
})

test('authors and units retain known source fields without fabricating metadata', () => {
  assert.equal(authorText(rows[0]), 'An Author')
  assert.equal(authorText(rows[1]), 'Another Author')
  assert.equal(affiliationText(rows[0]), 'HNUST')
  assert.equal(affiliationText(rows[1]), '')
  assert.equal(paperLink(rows[0]), 'https://example.com/award')
  assert.equal(paperLink({ paper_url: 'javascript:alert(1)', sources: [{ url: 'https://safe.example' }] }), 'https://safe.example/')
})

test('paper count is distinct from award row count and normalizes whitespace', () => {
  const same = [rows[0], rows[1], { ...rows[0], id: 'spacing', title: ' Learning   Memory ' }]
  assert.equal(overviewStats(same).papers, 1)
  assert.equal(overviewStats(same).records, 3)
  assert.equal(overviewStats([...same, {...rows[0], year:2025}]).papers, 2)
  assert.equal(overviewStats([...same, {...rows[0], acronym:'ACL'}]).papers, 2)
  assert.equal(overviewStats([{...rows[0],title:"Why Models Don't Memorize"}, {...rows[0],title:'Why Models Don’t Memorize'}]).papers,1)
})

test('CSV exports all filtered rows, escapes quotes and guards formulas', () => {
  const many = Array.from({ length: 250 }, (_, i) => ({ ...rows[0], id: String(i), title: i ? `Paper "${i}"` : ' =HYPERLINK("bad")' }))
  const csv = overviewCsv(overviewRows(many), { verified: '已核验' })
  assert.ok(csv.startsWith('\ufeff'))
  assert.equal(csv.split('\r\n').length, 251)
  assert.ok(csv.includes('"\' =HYPERLINK(""bad"")"'))
  assert.ok(csv.includes('"Paper ""249"""'))
  assert.ok(csv.includes('已核验'))
})

test('large multi-conference selections are not capped or deduplicated across awards', () => {
  const many = Array.from({ length: 3052 }, (_, i) => ({ ...rows[0], id: String(i), acronym: `C${i % 190}`, year: 1990 + i % 37 }))
  const conferences = Array.from({ length: 190 }, (_, i) => `C${i}`)
  assert.equal(overviewRows(many, { conferences, year_from: 1990, year_to: 2026 }).length, 3052)
})
