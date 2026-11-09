import { ref, watchEffect } from 'vue'
import { translate } from './translate.js'

function initialLocale() {
  try {
    const query = new URLSearchParams(window.location.search).get('lang')
    if (query === 'zh' || query === 'en') return query
    return localStorage.getItem('ccf-awards-language') === 'en' ? 'en' : 'zh'
  } catch { return 'zh' }
}
export const locale = ref(initialLocale())
export const t = value => translate(value, locale.value)
export function setLocale(value) {
  if (!['zh', 'en'].includes(value)) return
  locale.value = value
  try {
    localStorage.setItem('ccf-awards-language', value)
    const url = new URL(window.location.href)
    url.searchParams.set('lang', value)
    history.replaceState(null, '', url)
  } catch { /* Switching still works when browser storage is restricted. */ }
}
watchEffect(() => { document.documentElement.lang = locale.value === 'en' ? 'en' : 'zh-CN' })
