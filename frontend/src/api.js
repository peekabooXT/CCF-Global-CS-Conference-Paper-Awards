import axios from 'axios'
const http = axios.create({ baseURL: '/api', timeout: 60000 })
export const api = {
  meta: () => http.get('/meta').then(r => r.data),
  search: filters => http.post('/search', filters).then(r => r.data),
  exportUrl: filters => '/api/export/csv?q=' + encodeURIComponent(JSON.stringify(filters)),
  awardEvents: params => http.get('/award-events', { params }).then(r => r.data),
  awardEvent: id => http.get(`/award-events/${id}`).then(r => r.data),
  paperSources: id => http.get(`/papers/${encodeURIComponent(id)}/sources`).then(r => r.data),
}
export const errMsg = e => e?.response?.data?.detail || e?.message || '请求失败'
