import test from 'node:test'
import assert from 'node:assert/strict'
import { parseBatchYears, planCollectionBatches } from '../src/collectionBatches.js'

test('selection accepts more than twenty years', () => {
  assert.equal(parseBatchYears('1990-2026').length, 37)
  const plan = planCollectionBatches(['iccv'], '1990-2026')
  assert.equal(plan.totalTasks, 37)
  assert.equal(plan.chunks.length, 2)
  assert.deepEqual(plan.chunks.map(chunk => chunk.yearNumbers.length), [20, 17])
})

test('large selection is complete, unique, and bounded per confirmation', () => {
  const ids = Array.from({ length: 190 }, (_, index) => `conf-${index}`)
  const plan = planCollectionBatches(ids, '1980-2026')
  assert.equal(plan.totalTasks, 190 * 47)
  const pairs = new Set()
  for (const chunk of plan.chunks) {
    assert.ok(chunk.count > 0 && chunk.count <= 100)
    assert.ok(chunk.yearNumbers.length <= 20)
    assert.equal(chunk.count, chunk.conference_ids.length * chunk.yearNumbers.length)
    for (const id of chunk.conference_ids) {
      for (const year of chunk.yearNumbers) {
        const pair = `${id}:${year}`
        assert.ok(!pairs.has(pair), `duplicate ${pair}`)
        pairs.add(pair)
      }
    }
  }
  assert.equal(pairs.size, plan.totalTasks)
})

test('duplicate choices do not produce duplicate tasks', () => {
  const plan = planCollectionBatches(['acl', 'acl', 'iccv'], '2024,2024,2025')
  assert.equal(plan.totalTasks, 4)
  assert.equal(plan.chunks.length, 1)
})
