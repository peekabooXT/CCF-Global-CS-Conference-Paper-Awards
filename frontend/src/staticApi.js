import { decodeCatalog, searchStaticPapers, searchStaticEvents } from './staticSearch.js'

const bootstrap = () => {
  const element = document.getElementById('awards-static-data')
  if (!element) throw new Error('静态数据尚未生成，请重新构建并发布网站。')
  const data = JSON.parse(element.textContent)
  if (data.schema_version !== 1) throw new Error('静态数据版本不兼容，请刷新页面。')
  return data
}
const files = new Map()
function load(url) {
  const absolute = new URL(url, document.baseURI).href
  if (!files.has(absolute)) files.set(absolute, import(/* @vite-ignore */ absolute).then(async module => {
    const data = module.default
    if (!data.gzip) return data
    if (!globalThis.DecompressionStream) return load(data.fallback)
    const compressed = Uint8Array.from(atob(data.gzip), c => c.charCodeAt(0))
    return new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'))).json()
  }).catch(error => { files.delete(absolute); throw error }))
  return files.get(absolute)
}
let rowsPromise, defaultResult
const catalog = () => rowsPromise ||= load(bootstrap().catalog).then(decodeCatalog).catch(error => { rowsPromise = null; throw error })

export const api = {
  meta: async () => bootstrap().meta,
  search: async (filters = {}) => {
    const rows = await catalog()
    const unfiltered = !Object.entries(filters).some(([key, value]) => key !== 'status' && value != null && value !== '')
    if (unfiltered) return defaultResult ||= searchStaticPapers(rows)
    return searchStaticPapers(rows, filters)
  },
  awardEvents: async params => searchStaticEvents(await load(bootstrap().events), params),
  awardEvent: async id => {
    const config = bootstrap(), events = await load(config.events)
    const event = events.find(row => row.id === id)
    if (!event) throw new Error('获奖事件不存在')
    return (await load(config.event_chunks[event._chunk]))[id]
  },
  paperSources: async id => {
    const config = bootstrap(), rows = await catalog(), row = rows.find(item => item.id === id)
    if (!row) throw new Error('论文不存在或尚未核验')
    const data = await load(config.paper_chunks[Math.floor(row._group / config.paper_chunk_size)])
    return { ...data[row._group], record_id: id }
  },
}
export const errMsg = error => error?.message || '请求失败'
