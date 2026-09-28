"""Small UI-independent adapters; all search/collection rules stay in the core."""
import csv
import datetime as dt
import io
import json
import os
import re
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


def parse_years(value, max_years=20):
    """Parse `2024, 2021-2022, 2019` into unique descending years."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("请填写至少一个会议年份或年份区间。")
    years = set()
    for part in re.split(r"[,，;；\s]+", value):
        if not part:
            continue
        match = re.fullmatch(r"(\d{4})(?:\s*[-–—~至]\s*(\d{4}))?", part)
        if not match:
            raise ValueError(f"无法识别年份：{part}；示例：2023-2026, 2020")
        start, end = int(match.group(1)), int(match.group(2) or match.group(1))
        if not 1900 <= start <= 2200 or not 1900 <= end <= 2200:
            raise ValueError("年份应在 1900–2200 之间。")
        if start > end:
            raise ValueError(f"年份区间起点不能晚于终点：{part}")
        years.update(range(start, end + 1))
    if len(years) > max_years:
        raise ValueError(f"一次最多选择 {max_years} 个不同年份。")
    return sorted(years, reverse=True)


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


def run_log_csv_bytes(runs):
    """Flatten persisted collection runs into an Excel-friendly CSV."""
    rows = []
    for run in runs:
        details = run.get("details") or {}
        usage = details.get("token_usage") or {}
        search_usage = usage.get("search") or {}
        extraction_usage = usage.get("extraction") or {}
        search_tokens = search_usage.get("total_tokens")
        extraction_tokens = extraction_usage.get("total_tokens")
        known_tokens = [
            value for value in (search_tokens, extraction_tokens)
            if type(value) is int
        ]
        total_tokens = details.get("total_tokens")
        if type(total_tokens) is not int:
            total_tokens = sum(known_tokens) if known_tokens else ""
        rows.append({
            "任务": run.get("id", ""),
            "会议": run.get("acronym", ""),
            "年份": run.get("year", ""),
            "开始时间": run.get("started_at", ""),
            "结束时间": run.get("finished_at", ""),
            "耗时（秒）": run.get("duration_seconds") if run.get("duration_seconds") is not None else "",
            "状态": run.get("status", ""),
            "新增": details.get("inserted", 0),
            "更新": details.get("updated", 0),
            "重复": details.get("unchanged", 0),
            "搜索 tokens": search_tokens if type(search_tokens) is int else "",
            "提取 tokens": extraction_tokens if type(extraction_tokens) is int else "",
            "总 tokens": total_tokens,
            "说明": details.get("error", ""),
        })

    output = io.StringIO(newline="")
    fieldnames = [
        "任务", "会议", "年份", "开始时间", "结束时间", "耗时（秒）", "状态",
        "新增", "更新", "重复", "搜索 tokens", "提取 tokens", "总 tokens", "说明",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            value = str(value)
            safe[key] = "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
        writer.writerow(safe)
    return output.getvalue().encode("utf-8-sig")
