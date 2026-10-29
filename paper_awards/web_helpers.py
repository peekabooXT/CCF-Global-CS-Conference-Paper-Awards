import csv
import datetime as dt
import io
import json
import os
import re
from pathlib import Path
from .model import url_syntax
from .ontology import classify_award
AWARDS = {'best_paper': '最佳论文奖', 'best_student_paper': '最佳学生论文奖'}
STATUSES = {'active': '待核验与已核验', 'all': '全部状态', 'pending': '待核验', 'verified': '已核验', 'rejected': '已排除'}

def validate_filters(filters):
    for left, right in (('year_from', 'year_to'), ('published_from', 'published_to')):
        if filters.get(left) and filters.get(right) and (filters[left] > filters[right]):
            raise ValueError('起始时间不能晚于结束时间，请调整筛选条件。')
    return filters

def export_rows(records):
    rows = []
    for r in records:
        source = next((s['url'] for s in r['sources'] if s['id'] == (r.get('award_evidence') or {}).get('source_id')), r['sources'][0]['url'] if r['sources'] else '')
        is_listing = r.get('source_kind') == 'source_listing'
        rows.append({'论文名称': r['title'], '会议': r['acronym'], 'CCF': r['rank'], '会议年份': r['year'], '统一分类': r.get('category_label') or classify_award(r.get('award_name'))['category_label'], '奖项': r.get('award_name') or ('来源未提供原名' if is_listing else AWARDS.get(r['award_type'], r['award_type'])), '原始奖项': r.get('award_name') or '', '发表日期': r['publication_date'] or '未知', '日期精度': {'day': '日', 'month': '月', 'year': '年', 'unknown': '未知'}[r['date_precision']], '作者及单位': '; '.join((a['name'] + ' [' + ('; '.join((b['name'] for b in a['affiliations'])) or '单位未知') + ']' for a in r['authors'])) or r.get('authors_raw') or '未知', '状态': STATUSES[r['status']], '获奖来源': '' if is_listing else '\n'.join(dict.fromkeys((s['url'] for s in r['sources'] if s.get('role') != 'listing'))) or source, '聚合收录来源': '\n'.join(dict.fromkeys((s['url'] for s in r['sources'] if s.get('role') == 'listing'))) or (source if is_listing else ''), '论文链接': r['paper_url'] or '', 'DOI': r['doi'] or '', '记录编号': r['id']})
    return rows

def csv_bytes(records):
    rows = export_rows(records)
    if not rows:
        return b''
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            value = str(value)
            safe[key] = "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
        writer.writerow(safe)
    return output.getvalue().encode('utf-8-sig')
