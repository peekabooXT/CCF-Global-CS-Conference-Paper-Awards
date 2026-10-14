import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_PAGE_SIZE, DEFAULT_OVERVIEW_PAGE_SIZE, PAGE_SIZES, pageSlice } from '../src/pagination.js'

test('search defaults to five papers, overview to ten, with the requested sizes', () => {
  assert.equal(DEFAULT_PAGE_SIZE, 5)
  assert.equal(DEFAULT_OVERVIEW_PAGE_SIZE, 10)
  assert.deepEqual(PAGE_SIZES, [5, 10, 15, 20, 30, 50])
})

test('paging preserves all results, including a partial final page and no matches', () => {
  const rows = Array.from({ length: 53 }, (_, id) => id)
  for (const size of PAGE_SIZES) {
    const pages = Array.from({ length: Math.ceil(rows.length / size) }, (_, i) => pageSlice(rows, i + 1, size))
    assert.deepEqual(pages.flat(), rows)
    assert.ok(pages.every(page => page.length <= size))
  }
  assert.deepEqual(pageSlice(rows, 3, 20), rows.slice(40))
  assert.deepEqual(pageSlice([], 1, 5), [])
})
