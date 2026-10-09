"""Read-only export of year-sheet award/link workbooks for reviewed imports."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.model import keytext
from global_cs_paper_awards_agent.supplement_import import external_address
from global_cs_paper_awards_agent.public_data import publication_time

# Individually checked notation variants; never perform general fuzzy matching.
TITLE_VARIANTS = {
    ('PODS', 2026, r'Unbiased Insights: Optimal Streaming Algorithms for $\ell_p$ Sampling, the Forget Model, and Beyond'):
        'Unbiased Insights: Optimal Streaming Algorithms for ℓp Sampling, the Forget Model, and Beyond',
    ('SOSP', 2025, 'Rearchitecting the Thread Model of In-Memory Key-Value Stores with μTPS'):
        'Rearchitecting the Thread Model of In-Memory Key-Value Stores with muTPS',
    ('STOC', 2024, r'Single-Source Shortest Paths with Negative Real Weights in $\tilde O(mn^{8/9})$ Time'):
        'Single-Source Shortest Paths with Negative Real Weights in ˜ O (mn8/9) Time',
}


def export(source, target, database, verification_note):
    source = Path(source)
    book = load_workbook(source, read_only=True, data_only=True)
    db = Database(database, read_only=True)
    known = {(r['conference_id'], r['year'], keytext(r['title']))
             for r in db.conn.execute("SELECT conference_id,year,title FROM records WHERE status='verified'")}
    known.update((r['conference_id'], r['year'], keytext(r['title'])) for r in db.conn.execute('''
        SELECT DISTINCT e.conference_id,p.year,p.title FROM award_papers p
        JOIN award_event_papers x ON x.paper_id=p.id JOIN award_events e ON e.id=x.event_id'''))
    rows = []
    try:
        for sheet in book:
            values = sheet.values
            next(values)
            headers = next(values)
            required = {'会议简称','获奖年份','论文题目','奖项名称','官方获奖链接','公开下载地址'}
            if not required.issubset(headers):
                raise ValueError(f'工作表字段不完整：{sheet.title}')
            for index, cells in enumerate(values, 3):
                if not any(c is not None for c in cells):
                    continue
                original = dict(zip(headers, cells))
                conference = db.resolve(str(original['会议简称']).split('（')[0])
                year = int(original['获奖年份'])
                title = str(original['论文题目']).strip()
                canonical = TITLE_VARIANTS.get((conference['acronym'], year, title), title)
                if conference['acronym'] == 'ETAPS':
                    candidate = re.sub(r'\s*(?:\((?:ESOP|FoSSaCS|TACAS|FASE)\)|\.\s*(?:ESOP|FoSSaCS|TACAS|FASE)\s+20\d{2})$', '', title)
                    if (conference['id'], year, keytext(candidate)) in known:
                        canonical = candidate
                rows.append(dict(sheet=sheet.title,row=index,conference_id=conference['id'],
                    venue=conference['acronym'],year=year,title=title,canonical_title=canonical,
                    award_name=str(original['奖项名称']).strip(),authors_raw=original.get('作者（含官网所列单位）'),
                    source_url=external_address(original['官方获奖链接']),
                    paper_url=external_address(original.get('公开下载地址')),original=original))
    finally:
        book.close()
        db.close()
    document = dict(format='reviewed-public-link-supplement-v1',source_workbook=source.name,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),imported_at=publication_time(),
        review_status='verified',verification_note=verification_note,records=rows)
    Path(target).parent.mkdir(parents=True,exist_ok=True)
    Path(target).write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dict(rows=len(rows),title_variants=sum(r['title']!=r['canonical_title'] for r in rows),
                external_links=sum(bool(r['paper_url']) for r in rows))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('target'); parser.add_argument('--database',required=True)
    parser.add_argument('--verification-note',required=True)
    args=parser.parse_args()
    print(json.dumps(export(args.source,args.target,args.database,args.verification_note),ensure_ascii=False))
