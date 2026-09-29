import axios from 'axios'

// 统一的 HTTP 封装：所有接口只在这里出现一次，页面组件直接 import { api }
const http = axios.create({ baseURL: '/api', timeout: 600000 })

export const api = {
  meta: () => http.get('/meta').then(r => r.data),
  awardEvents: (params) => http.get('/award-events', { params }).then(r => r.data),
  awardEvent: (id) => http.get(`/award-events/${id}`).then(r => r.data),
  sourceListings: (params) => http.get('/source-listings', { params }).then(r => r.data),
  sourceListing: (id) => http.get(`/source-listings/${id}`).then(r => r.data),

  search: (filters) => http.post('/search', filters).then(r => r.data),
  exportUrl: (filters) => '/api/export/csv?q=' + encodeURIComponent(JSON.stringify(filters)),

  review: (body) => http.post('/review', body).then(r => r.data),

  coverage: (q) => http.get('/coverage', { params: q }).then(r => r.data),
  markCoverage: (body) => http.post('/mark-coverage', body).then(r => r.data),

  seedStats: () => http.get('/seed-stats').then(r => r.data),
  seeds: (cid, year) => http.get(`/seeds/${cid}/${year}`).then(r => r.data),
  addSeed: (body) => http.post('/seeds', body).then(r => r.data),

  importJson: (body) => http.post('/import', body).then(r => r.data),
  demo: () => http.post('/demo').then(r => r.data),
  runs: (limit = 50) => http.get('/runs', { params: { limit } }).then(r => r.data),
  runExportUrl: (limit = 500) => `/api/runs/export/csv?limit=${encodeURIComponent(limit)}`,
}

// 统一错误提示：后端返回 {detail: "..."}
export function errMsg(e) {
  return e?.response?.data?.detail || e?.message || '请求失败'
}

// 读取 SSE 流：后端按 "data: {json}\n\n" 推送 log/result/error
async function readSSE(res, onLog) {
  if (!res.ok || !res.body) throw new Error('服务端无响应')
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
      const line = chunk.replace(/^data:\s?/, '').trim()
      if (!line) continue
      const evt = JSON.parse(line)
      if (evt.type === 'log') onLog(evt.message)
      else if (evt.type === 'result') result = evt.result
      else if (evt.type === 'error') throw new Error(evt.message)
    }
  }
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

// 上传文件采集：POST FormData，实时滚动日志
export function collectFilesStream(formData, onLog) {
  return fetch('/api/collect-files-stream', {
    method: 'POST',
    body: formData,
  }).then(res => readSSE(res, onLog))
}
