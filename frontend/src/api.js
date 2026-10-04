import axios from 'axios'

// 统一的 HTTP 封装：所有接口只在这里出现一次，页面组件直接 import { api }
const http = axios.create({ baseURL: '/api', timeout: 600000 })

export const api = {
  meta: () => http.get('/meta').then(r => r.data),
  llmModels: (llm) => http.post('/llm-models', llm).then(r => r.data),
  awardEvents: (params) => http.get('/award-events', { params }).then(r => r.data),
  awardEvent: (id) => http.get(`/award-events/${id}`).then(r => r.data),
  sourceListings: (params) => http.get('/source-listings', { params }).then(r => r.data),
  sourceListing: (id) => http.get(`/source-listings/${id}`).then(r => r.data),

  search: (filters) => http.post('/search', filters).then(r => r.data),
  exportUrl: (filters) => '/api/export/csv?q=' + encodeURIComponent(JSON.stringify(filters)),
  exportBatchCsv: (recordIds) => http.post('/export/batch-csv', { record_ids: recordIds }, { responseType: 'blob' }).then(r => r.data),

  review: (body) => http.post('/review', body).then(r => r.data),

  coverage: (q) => http.get('/coverage', { params: q }).then(r => r.data),
  queryCoverage: (body) => http.post('/coverage/query', body).then(r => r.data),
  markCoverage: (body) => http.post('/mark-coverage', body).then(r => r.data),

  seedStats: () => http.get('/seed-stats').then(r => r.data),
  seeds: (cid, year) => http.get(`/seeds/${cid}/${year}`).then(r => r.data),
  lookupSeeds: (conferenceIds, years) => http.post('/seeds/lookup', { conference_ids: conferenceIds, years }).then(r => r.data),
  addSeed: (body) => http.post('/seeds', body).then(r => r.data),
  replaceSeeds: (body) => http.put('/seeds', body).then(r => r.data),

  importJson: (body) => http.post('/import', body).then(r => r.data),
  demo: () => http.post('/demo').then(r => r.data),
  runs: (params = {}) => http.get('/runs', { params: { limit: 50, ...params } }).then(r => r.data),
  runExportUrl: (params = {}) => `/api/runs/export/csv?${new URLSearchParams(params).toString()}`,
  runDeletionPreview: (params) => http.get('/runs/deletion-preview', { params }).then(r => r.data),
  deleteRuns: (body) => http.post('/runs/delete', body).then(r => r.data),
}

// 统一错误提示：后端返回 {detail: "..."}
export function errMsg(e) {
  return e?.response?.data?.detail || e?.message || '请求失败'
}

// 读取 SSE 流：后端按 "data: {json}\n\n" 推送 log/result/error
async function readSSE(res, onLog, onTask = () => {}) {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `采集请求失败（HTTP ${res.status}）`)
  }
  if (!res.body) throw new Error('服务端无响应')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const chunk of chunks) {
      if (!chunk.startsWith('data:')) continue
      const line = chunk.replace(/^data:\s?/, '').trim()
      if (!line) continue
      const evt = JSON.parse(line)
      if (evt.type === 'log') onLog(evt.message)
      else if (evt.type === 'task') onTask(evt.task)
      else if (evt.type === 'result') result = evt.result
      else if (evt.type === 'error') throw new Error(evt.message)
    }
  }
  if (result === null) throw new Error('采集连接已结束，但没有收到最终结果；请检查运行日志')
  return result
}

// 网址/自动采集：POST JSON，实时滚动日志
export function collectStream(body, onLog) {
  return fetch('/api/collect-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(res => readSSE(res, onLog))
}

export function collectBatchStream(body, onLog, onTask) {
  return fetch('/api/collect-batch-stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(res => readSSE(res, onLog, onTask))
}

// 上传文件采集：POST FormData，实时滚动日志
export function collectFilesStream(formData, onLog) {
  return fetch('/api/collect-files-stream', {
    method: 'POST',
    body: formData,
  }).then(res => readSSE(res, onLog))
}
