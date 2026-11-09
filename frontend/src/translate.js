import english from './messages.en.js'

// Only interface strings are passed here. Paper titles, original award names,
// authors and evidence remain source data in both languages.
export function translate(value, language = 'zh') {
  if (value == null || typeof value !== 'string' || language !== 'en') return value
  if (english[value]) return english[value]
  const trimmed = value.trim()
  if (english[trimmed]) return value.replace(trimmed, english[trimmed])
  return value
    .replace(/^共检索到 ([\d,]+) 篇论文$/, '$1 papers found')
    .replace(/ 等 (\d+) 位$/, ' and $1 authors')
    .replace(/ · (\d+) 条$/, ' · $1 records')
    .replace(/ · 未映射/g, ' · Unmapped')
    .replace(/ · 在 Google Scholar 检索（外部网站）$/, ' · Search Google Scholar (external website)')
    .replace(/^查看(.+)老师的介绍（新窗口）$/, (_, name) => `Profile of ${english[name] || name} (opens in a new tab)`)
    .replace(/CCF ([AB]) 类会议/g, 'CCF $1 conference')
    .replace(/ · ([AB]) 类 · /g, ' · CCF $1 · ')
}
