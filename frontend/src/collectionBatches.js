// The server still caps each request at 100 targets and 20 years. The UI may
// select more, but it only sends one bounded batch after each user confirmation.
export const TASKS_PER_BATCH = 100
export const YEARS_PER_BATCH = 20

export function parseBatchYears(value) {
  const years = new Set()
  for (const part of String(value || '').split(/[,，;；\s]+/).filter(Boolean)) {
    const match = part.match(/^(\d{4})(?:[-–—~至](\d{4}))?$/)
    if (!match) throw new Error(`无法识别年份：${part}；示例：2022-2026, 2020`)
    const start = Number(match[1])
    const end = Number(match[2] || match[1])
    if (start < 1900 || end > 2200 || start > end) throw new Error(`年份区间不正确：${part}`)
    for (let year = start; year <= end; year++) years.add(year)
  }
  if (!years.size) throw new Error('请至少填写一个年份')
  return [...years].sort((a, b) => b - a)
}

export function planCollectionBatches(conferenceIds, yearText) {
  const ids = [...new Set(conferenceIds)]
  if (!ids.length) throw new Error('请至少选择一个会议')
  const years = parseBatchYears(yearText)
  const chunks = []
  for (let offset = 0; offset < ids.length; offset += TASKS_PER_BATCH) {
    const conference_ids = ids.slice(offset, offset + TASKS_PER_BATCH)
    const yearsPerChunk = Math.min(YEARS_PER_BATCH, Math.floor(TASKS_PER_BATCH / conference_ids.length))
    for (let start = 0; start < years.length; start += yearsPerChunk) {
      const yearNumbers = years.slice(start, start + yearsPerChunk)
      chunks.push({
        conference_ids,
        yearNumbers,
        years: yearNumbers.join(','),
        count: conference_ids.length * yearNumbers.length,
      })
    }
  }
  return { chunks, totalTasks: ids.length * years.length, totalYears: years.length }
}
