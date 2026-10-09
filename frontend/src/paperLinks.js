// External navigation only: never fetch, proxy, mirror or download a paper here.
export function externalUrl(value, siteHost = globalThis.location?.hostname || '') {
  try {
    if (!/^https?:\/\//i.test(String(value || '').trim())) return ''
    const url = new URL(value)
    const host = url.hostname.toLowerCase().replace(/\.$/, '')
    const current = siteHost.toLowerCase().replace(/\.$/, '')
    if (url.username || url.password || host === current || host === '47.107.172.42' ||
        host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
        /^(127\.|10\.|192\.168\.|169\.254\.|0\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) ||
        host === '[::1]' || host === '[::]' || /^\[(fc|fd|fe80:)/i.test(host)) return ''
    return url.href
  } catch { return '' }
}

function savedScholarUrl(value) {
  const address = externalUrl(value)
  if (!address) return ''
  const url = new URL(address)
  return ['scholar.google.com', 'scholar.google.com.hk'].includes(url.hostname) && url.pathname === '/scholar'
    ? address : ''
}

export function scholarUrl(record, listings = []) {
  // Retain source-provided exact-title/author parameters (e.g. Ozaki) when available.
  for (const address of [record.discovery_url, ...listings.map(item => item.discovery_url), record.paper_url]) {
    const saved = savedScholarUrl(address)
    if (saved) return saved
  }
  const title = String(record.title || '').trim()
  if (!title) return ''
  // Do not guess surnames from raw strings or risk excluding a match with a bad author filter.
  return 'https://scholar.google.com/scholar?' + new URLSearchParams({
    as_q: '', num: '10', btnG: 'Search Scholar', as_epq: title,
    as_oq: '', as_eq: '', as_occt: 'any', as_sauthors: '',
  })
}

export function externalPaperUrl(record) {
  const url = externalUrl(record.paper_url)
  return savedScholarUrl(url) ? '' : url
}

export function sourceUrl(record) {
  return (record.sources || []).map(source => externalUrl(source.url)).find(Boolean) || ''
}
