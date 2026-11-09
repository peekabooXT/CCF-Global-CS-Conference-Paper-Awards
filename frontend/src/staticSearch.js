// Static public search follows source-level filtering before paper merging.
export const fold = value => String(value ?? '').normalize('NFKC').toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ').trim().replace(/\s+/gu, ' ')
const titleKey = value => fold(value).replace(/[‘’]/gu, "'").replace(/[“”]/gu, '"')
const unique = values => [...new Set(values)]

export function decodeCatalog(catalog) {
  return catalog.rows.map(values => Object.fromEntries(catalog.columns.map((key, i) => [key, values[i]])))
}

export function mergeStaticPapers(rows) {
  const groups = new Map()
  for (const row of rows) {
    if (!groups.has(row._group)) groups.set(row._group, [])
    groups.get(row._group).push(row)
  }
  return [...groups].sort(([a], [b]) => a - b).map(([, members]) => {
    const primary = members.find(row => row.authors?.length) || members[0]
    const item = { ...primary }, awards = new Map(), sources = new Map()
    item.related_record_ids = unique(members.map(row => row.id))
    for (const row of members) {
      if (row.award_name && !awards.has(titleKey(row.award_name))) awards.set(titleKey(row.award_name), Object.fromEntries(['id', 'event_id', 'award_name', 'category', 'category_label', 'status'].map(k => [k, row[k] ?? null])))
      for (const source of row.sources || []) sources.set(JSON.stringify([source.id ?? null, source.url ?? null]), source)
    }
    item.awards = [...awards.values()]
    item.award_name = item.awards.map(award => award.award_name).join('；') || null
    item.categories = unique(members.map(row => row.category))
    item.category_labels = unique(members.map(row => row.category_label))
    item.category_label = item.category_labels.join(' / ')
    item.sources = [...sources.values()]
    for (const field of ['paper_url', 'doi', 'discovery_url', 'authors_raw', 'publication_date']) item[field] = members.find(row => row[field])?.[field] ?? item[field]
    return item
  })
}

export function searchStaticPapers(rows, filters = {}) {
  const f = filters
  const matches = rows.filter(row => {
    if (f.conference && row.conference_id !== f.conference) return false
    if (f.rank && row.rank !== f.rank) return false
    if (f.year_from != null && row.year < f.year_from) return false
    if (f.year_to != null && row.year > f.year_to) return false
    if (f.category && row.category !== f.category) return false
    if (f.title && !fold(row.title).includes(fold(f.title))) return false
    if (f.award_name && (row.source_kind === 'source_listing' || fold(row.award_name) !== fold(f.award_name))) return false
    if (f.award && (!row._legacy || row.award_type !== f.award)) return false
    if (row._legacy) {
      if ((f.author || f.affiliation) && !(row.authors || []).some(author => (!f.author || fold(author.name).includes(fold(f.author))) && (!f.affiliation || (author.affiliations || []).some(a => fold(a.name).includes(fold(f.affiliation)))))) return false
      if (f.published_from && (!row.date_end || row.date_end < f.published_from)) return false
      if (f.published_to && (!row.date_start || row.date_start > f.published_to)) return false
    } else {
      if (f.affiliation || f.published_from || f.published_to) return false
      if (f.author && !fold(row.authors_raw).includes(fold(f.author))) return false
    }
    return true
  })
  const legacyKeys = new Set(matches.filter(row => row._legacy).map(row => row._duplicate_key))
  const records = mergeStaticPapers(matches.filter(row => row._legacy || row.source_kind !== 'award_event' || !legacyKeys.has(row._duplicate_key)))
  return { total: records.length, records }
}

export function searchStaticEvents(events, { venue = '', category = '', query = '', limit = 100, offset = 0 } = {}) {
  const rows = events.filter(event => (!venue || fold(event.venue).includes(fold(venue))) && (!category || event.category === category) && (!query || event._query.some(text => text.includes(fold(query)))))
  return { total: rows.length, events: rows.slice(offset, offset + limit) }
}
