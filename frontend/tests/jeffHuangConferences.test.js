import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { JEFF_HUANG_VENUES, selectJeffHuangConferences } from '../src/jeffHuangConferences.js'

const catalog = JSON.parse(readFileSync(new URL('../../data/conferences.json', import.meta.url), 'utf8'))

test('Jeff Huang preset maps all 32 venues to distinct catalog conferences', () => {
  const { ids, unmatched } = selectJeffHuangConferences(catalog)
  assert.equal(JEFF_HUANG_VENUES.length, 32)
  assert.deepEqual(unmatched, [])
  assert.equal(ids.length, 32)
  assert.equal(new Set(ids).size, 32)
  assert.equal(catalog.find(conference => conference.id === ids[JEFF_HUANG_VENUES.indexOf('KDD')]).acronym, 'SIGKDD')
  assert.match(catalog.find(conference => conference.id === ids[JEFF_HUANG_VENUES.indexOf('FSE')]).full_name,
    /Foundations of Software Engineering/)
})

test('preset reports missing or ambiguous catalog matches', () => {
  const { ids, unmatched } = selectJeffHuangConferences(catalog.filter(conference => conference.acronym !== 'AAAI'))
  assert.equal(ids.length, 31)
  assert.deepEqual(unmatched, ['AAAI'])
})
