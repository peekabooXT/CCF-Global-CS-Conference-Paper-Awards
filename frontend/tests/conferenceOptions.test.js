import test from 'node:test'
import assert from 'node:assert/strict'
import { alphabeticalConferences } from '../src/conferenceOptions.js'

test('conference options use acronym A-Z instead of area or CCF rank', () => {
  const conferences = [
    { id: 5, acronym: 'RTSS', rank: 'A', area: 'Cross-disciplinary' },
    { id: 4, acronym: 'WWW', rank: 'A' },
    { id: 3, acronym: 'BIBM', rank: 'B' },
    { id: 2, acronym: 'ACL', rank: 'A' },
    { id: 1, acronym: 'AAAI', rank: 'A' },
    { id: 6, acronym: 'CogSci', rank: 'B' },
  ]
  const original = [...conferences]
  const sorted = alphabeticalConferences(conferences)
  assert.deepEqual(sorted.map(c => c.acronym), ['AAAI', 'ACL', 'BIBM', 'CogSci', 'RTSS', 'WWW'])
  assert.deepEqual(conferences, original)
  assert.equal(sorted[0], conferences[4])
})

test('sorting ignores case and keeps conference identifiers and empty input intact', () => {
  assert.deepEqual(alphabeticalConferences(), [])
  assert.deepEqual(alphabeticalConferences([
    { id: 'z', acronym: 'ZED' }, { id: 'b', acronym: 'beta' }, { id: 'a', acronym: 'Alpha' },
  ]).map(c => c.id), ['a', 'b', 'z'])
})
