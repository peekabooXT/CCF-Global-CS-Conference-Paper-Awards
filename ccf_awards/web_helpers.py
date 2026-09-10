"""Small UI-independent adapters; all search/collection rules stay in the core."""
import csv
import datetime as dt
import io
import json
import os
from pathlib import Path
from .model import url_syntax

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AWARDS = {"best_paper": "最佳论文奖", "best_student_paper": "最佳学生论文奖"}
STATUSES = {"active": "待核验与已核验", "all": "全部状态", "pending": "待核验", "verified": "已核验", "rejected": "已排除"}
COVERAGE = {"not_started": "尚未开始", "partial": "部分记录", "checked": "已检查名单", "not_offered": "确认未设奖", "not_found": "暂未找到"}


def database_path():
    path = Path(os.getenv("CCF_AWARDS_DB", "data/awards.sqlite3")).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def validate_filters(filters):
    for left, right in (("year_from", "year_to"), ("published_from", "published_to")):
        if filters.get(left) and filters.get(right) and filters[left] > filters[right]:
            raise ValueError("起始时间不能晚于结束时间，请调整筛选条件。")
    return filters


def urls_from_text(value):
    urls = list(dict.fromkeys(line.strip() for line in value.splitlines() if line.strip()))
    for url in urls:
        url_syntax(url)
    return urls


def import_demo(db):
    return [db.ingest(json.loads(path.read_text(encoding="utf-8")))
            for path in sorted((PROJECT_ROOT / "examples").glob("sample-*.json"))]


def export_rows(records):
    rows = []
    for r in records:
        source = next(s["url"] for s in r["sources"] if s["id"] == r["award_evidence"]["source_id"])
        rows.append({"论文名称": r["title"], "会议": r["acronym"], "CCF": r["rank"],
                     "会议年份": r["year"], "奖项": AWARDS[r["award_type"]],
                     "原始奖项": r["award_name"], "发表日期": r["publication_date"] or "未知",
                     "日期精度": {"day":"日", "month":"月", "year":"年", "unknown":"未知"}[r["date_precision"]],
                     "作者及单位": "; ".join(a["name"] + " [" + ("; ".join(b["name"] for b in a["affiliations"]) or "单位未知") + "]" for a in r["authors"]) or "未知",
                     "状态": STATUSES[r["status"]], "获奖来源": source,
                     "论文链接": r["paper_url"] or "", "DOI": r["doi"] or "", "记录编号": r["id"]})
    return rows


def csv_bytes(records):
    rows = export_rows(records)
    if not rows:
        return b""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            value = str(value)
            safe[key] = "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")
