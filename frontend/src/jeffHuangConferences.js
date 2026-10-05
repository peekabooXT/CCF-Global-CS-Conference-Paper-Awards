// Conference names from https://jeffhuang.com/best_paper_awards/conferences.html
export const JEFF_HUANG_VENUES = [
  'AAAI', 'ACL', 'CHI', 'CIKM', 'CVPR', 'FOCS', 'FSE', 'ICCV',
  'ICML', 'ICSE', 'IJCAI', 'INFOCOM', 'KDD', 'MOBICOM', 'NEURIPS',
  'NSDI', 'OSDI', 'PLDI', 'PODS', 'S&P', 'SIGCOMM', 'SIGGRAPH',
  'SIGIR', 'SIGMETRICS', 'SIGMOD', 'SODA', 'SOSP', 'STOC',
  'UIST', 'VLDB', 'WWW', 'ISCA',
]

export function selectJeffHuangConferences(conferences) {
  const ids = []
  const unmatched = []
  for (const venue of JEFF_HUANG_VENUES) {
    const candidates = conferences.filter(conference =>
      [conference.acronym, ...(conference.aliases || [])]
        .some(name => name?.toUpperCase() === venue))
    const matches = venue === 'FSE'
      ? candidates.filter(conference => conference.full_name?.includes('Foundations of Software Engineering'))
      : candidates
    if (matches.length === 1) ids.push(matches[0].id)
    else unmatched.push(venue)
  }
  return { ids, unmatched }
}
