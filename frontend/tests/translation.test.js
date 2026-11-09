import test from 'node:test'
import assert from 'node:assert/strict'
import { translate } from '../src/translate.js'
import { overviewCsv } from '../src/paperOverview.js'

test('Chinese is unchanged and English translates UI labels and dynamic counts', () => {
  assert.equal(translate('论文总览'), '论文总览')
  assert.equal(translate('论文总览', 'en'), 'Paper overview')
  assert.equal(translate('共检索到 4,942 篇论文', 'en'), '4,942 papers found')
  assert.equal(translate('Chen 等 3 位', 'en'), 'Chen and 3 authors')
})
test('unknown strings and source text are not guessed or rewritten', () => {
  for (const text of ['An Original Paper Title', 'Outstanding Paper – Research Track', '原始来源证据']) {
    assert.equal(translate(text, 'en'), text)
  }
})
test('English CSV changes UI headers and statuses while preserving paper identity', () => {
  const record={id:'record-1',acronym:'SIGIR',rank:'A',year:2025,title:'Original title',authors_raw:'Zhang',category_label:'最佳论文奖',award_name:'Original award name',status:'verified'}
  const original=JSON.stringify(record)
  const csv=overviewCsv([record],{verified:'已核验'},'en')
  assert.match(csv, /Paper title/)
  assert.match(csv, /Verified/)
  assert.match(csv, /Original title/)
  assert.match(csv, /Original award name/)
  assert.equal(JSON.stringify(record),original)
})
