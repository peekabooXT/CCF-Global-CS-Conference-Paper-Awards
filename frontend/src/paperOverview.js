// Presentation-only helpers. Award identities and review status are never changed.
const fold = value => String(value ?? '').normalize('NFKC').toLocaleLowerCase().trim()
const compare = (a, b) => String(a ?? '').localeCompare(String(b ?? ''), 'en', { numeric: true, sensitivity: 'base' })

export function authorText(record) {
  return record.authors?.length
    ? record.authors.map(author => author.name).filter(Boolean).join('; ')
    : record.authors_raw || ''
}

export function affiliationText(record) {
  return [...new Set((record.authors || []).flatMap(author =>
    (author.affiliations || []).map(affiliation => affiliation.name).filter(Boolean)))].join('; ')
}

export function paperLink(record) {
  const candidates = [record.paper_url, ...(record.sources || []).map(source => source.url)]
  return candidates.find(url => /^https?:\/\//i.test(url || '')) || ''
}

export function overviewRows(records, filters = {}, sort = 'conference') {
  const conferences = new Set((filters.conferences || []).map(fold))
  const words = fold(filters.query).split(/\s+/).filter(Boolean)
  const rows = records.filter(record => {
    if (conferences.size && !conferences.has(fold(record.acronym))) return false
    if (filters.rank && record.rank !== filters.rank) return false
    if (filters.category && record.category !== filters.category) return false
    if (filters.status && !['active', 'all'].includes(filters.status) && record.status !== filters.status) return false
    if (filters.status === 'active' && record.status === 'rejected') return false
    if (filters.year_from != null && record.year < filters.year_from) return false
    if (filters.year_to != null && record.year > filters.year_to) return false
    const text = fold([record.title, record.acronym, record.year, record.award_name,
      record.category_label, authorText(record), affiliationText(record)].join(' '))
    return words.every(word => text.includes(word))
  })
  // Stable tie breakers retain separate records when one paper receives multiple awards.
  const conferenceOrder = (a, b) => compare(a.acronym, b.acronym) || b.year - a.year
  rows.sort((a, b) => {
    const primary = sort === 'year' ? b.year - a.year || compare(a.acronym, b.acronym)
      : sort === 'title' ? compare(a.title, b.title) : conferenceOrder(a, b)
    return primary || compare(a.title, b.title) || compare(a.award_name, b.award_name) || compare(a.id, b.id)
  })
  return rows
}

export function overviewStats(records) {
  const years = records.map(record => record.year).filter(Number.isFinite)
  return {
    records: records.length,
    conferences: new Set(records.map(record => fold(record.acronym))).size,
    papers: new Set(records.map(record => JSON.stringify([fold(record.acronym), record.year, fold(record.title)]))).size,
    yearFrom: years.length ? Math.min(...years) : null,
    yearTo: years.length ? Math.max(...years) : null,
  }
}

export function overviewCsv(records, statuses = {}) {
  const cell = value => {
    let text = String(value ?? '')
    // Prevent spreadsheet formula execution, including values with leading whitespace.
    if (/^\s*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text
    return '"' + text.replaceAll('"', '""') + '"'
  }
  const rows = [['会议', 'CCF', '获奖年份', '论文题名', '作者', '作者单位', '统一分类', '奖项原名', '核验状态', '发表日期', '论文或来源链接', '记录ID']]
  for (const record of records) rows.push([record.acronym, record.rank, record.year, record.title,
    authorText(record), affiliationText(record), record.category_label, record.award_name || '来源未提供',
    statuses[record.status] || record.status, record.publication_date || '未知', paperLink(record), record.id])
  return '\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n')
}
