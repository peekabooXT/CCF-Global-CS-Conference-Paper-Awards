"""Read-only overlap audit for the supplied JeffHuang workbook."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ccf_awards.award_events import venue_for
from ccf_awards.model import keytext, norm
from ccf_awards.ontology import classify_award
from ccf_awards.source_listings import TITLE_ALIASES


def main(workbook_path, evidom_path, verified_path):
    catalog = json.loads(Path('data/conferences.json').read_text(encoding='utf-8'))
    venue_ids = {}
    for item in catalog:
        for alias in [item['acronym'], *item.get('aliases', [])]:
            venue_ids.setdefault(norm(alias), set()).add(item['id'])
    software_fse = next(item['id'] for item in catalog
                        if norm(item['acronym']) == 'fse'
                        and 'foundations of software engineering' in norm(item['full_name']))
    def venue(value, area=''):
        if norm(value) == 'fse' and norm(area) == 'software engineering':
            return software_fse
        ids = venue_ids.get(norm(value), set())
        return next(iter(ids)) if len(ids) == 1 else norm(value)
    book = load_workbook(workbook_path, read_only=True, data_only=True)
    rows = [r for r in list(book['Papers'].values)[4:] if len(r) >= 7 and r[4]]
    evidom = json.loads(Path(evidom_path).read_text(encoding='utf-8'))['records']
    verified = json.loads(Path(verified_path).read_text(encoding='utf-8'))['records']
    ek = defaultdict(list)
    for r in evidom:
        ek[(venue(venue_for(r['page_id'], r['official_award_name'])), int(r['year']), keytext(r['title']))].append(r)
    vk = defaultdict(list)
    for r in verified:
        vk[(r['conference_id'], int(r['year']), keytext(r['record']['title']))].append(r)
    seen = defaultdict(list)
    for r in rows:
        title_key = TITLE_ALIASES.get((norm(r[2]), int(r[1]), keytext(r[4])), keytext(r[4]))
        seen[(venue(r[2], r[3]), int(r[1]), title_key)].append(r)
    e_matches = [(k, v, ek[k]) for k, v in seen.items() if k in ek]
    v_matches = [(k, v, vk[k]) for k, v in seen.items() if k in vk]
    print('rows', len(rows), 'unique_keys', len(seen), 'within_duplicates', sum(len(v)-1 for v in seen.values()))
    print('evidom_overlap_keys', len(e_matches), 'verified_overlap_keys', len(v_matches))
    print('evidom_normalized_duplicate_keys', sum(len(v)>1 for v in ek.values()),
          'verified_normalized_duplicate_keys', sum(len(v)>1 for v in vk.values()))
    print('overlap_union', sum(k in ek or k in vk for k in seen),
          'only_verified', sum(k in vk and k not in ek for k in seen),
          'both', sum(k in vk and k in ek for k in seen))
    print('evidom_categories', Counter(classify_award(e[0]['official_award_name'])['category'] for _,_,e in e_matches))
    print('evidom_samples')
    for key, jr, er in e_matches[:12]:
        print(key[1], jr[0][2], jr[0][4], '=>', er[0]['official_award_name'])
    print('workbook_duplicates')
    for key, v in list((k,v) for k,v in seen.items() if len(v)>1)[:15]:
        print(key, [x[0] for x in v])
    cross = defaultdict(list)
    for r in evidom:
        cross[(int(r['year']),keytext(r['title']))].append(venue_for(r['page_id'],r['official_award_name']))
    mismatches = [(r[0],r[2],r[4],cross[(int(r[1]),keytext(r[4]))]) for r in rows
                  if (int(r[1]),keytext(r[4])) in cross and (venue(r[2],r[3]),int(r[1]),keytext(r[4])) not in ek]
    print('same_title_year_different_venue',len(mismatches),mismatches[:10])
    by_edition = defaultdict(list)
    existing_title = {}
    for key in set(ek) | set(vk):
        by_edition[key[:2]].append(key[2])
        existing_title[key] = (ek[key][0]['title'] if key in ek else vk[key][0]['record']['title'])
    near = []
    for key, source_rows in seen.items():
        if key in ek or key in vk:
            continue
        candidate = max((SequenceMatcher(None, key[2], other).ratio(), other)
                        for other in by_edition[key[:2]] if other != key[2]) if any(
                            other != key[2] for other in by_edition[key[:2]]) else (0, '')
        if candidate[0] >= .94:
            near.append((round(candidate[0], 3), source_rows[0][0], source_rows[0][1],
                         source_rows[0][2], source_rows[0][4], existing_title[(*key[:2],candidate[1])]))
    print('near_title_candidates_094',len(near))
    for item in sorted(near, reverse=True)[:20]:
        print(item)
        key = next(k for k,v in seen.items() if v[0][0] == item[1])
        target = next((k for k in set(ek)|set(vk) if k[:2]==key[:2] and existing_title[k]==item[5]),None)
        if target:
            print('authors', seen[key][0][5], '=>',
                  ek[target][0].get('authors_raw') if target in ek else
                  [a.get('name') for a in vk[target][0]['record'].get('authors',[])])


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('workbook')
    parser.add_argument('evidom')
    parser.add_argument('verified')
    args=parser.parse_args()
    main(args.workbook,args.evidom,args.verified)
