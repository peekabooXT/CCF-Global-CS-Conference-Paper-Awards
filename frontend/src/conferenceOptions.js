// Sort presentation options without changing the shared conference metadata.
export function alphabeticalConferences(conferences = []) {
  const compare = (a, b) => String(a ?? '').trim().localeCompare(
    String(b ?? '').trim(), 'en', { sensitivity: 'base', numeric: true })
  return [...conferences].sort((a, b) =>
    compare(a.acronym, b.acronym) || compare(a.id, b.id))
}
