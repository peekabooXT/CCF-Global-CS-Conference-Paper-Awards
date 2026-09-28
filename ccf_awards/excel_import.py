"""Import the curated award workbook into the application's SQLite database."""
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

from .model import date_bounds, now

IMPORT_REVIEWER = "Excel核验整理版"


def _text(value):
    return str(value).strip() if value is not None else ""


def _url(value):
    value = _text(value)
    return value if value.startswith(("https://", "http://")) else None


def _iso_date(value, fallback_year=None):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.date().isoformat() if isinstance(value, dt.datetime) else value.isoformat()
    value = _text(value)
    if value:
        match = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", value)
        if match:
            parts = [match.group(1)]
            parts.extend(part.zfill(2) for part in match.groups()[1:] if part)
            return "-".join(parts)
    return str(int(fallback_year)) if fallback_year else None


def _rows(sheet):
    iterator = sheet.iter_rows(values_only=True)
    headers = [_text(value) for value in next(iterator)]
    return headers, [dict(zip(headers, row)) for row in iterator if any(value not in (None, "") for value in row)]


def _conference(db, acronym, full_name=None):
    candidates = [_text(acronym), re.sub(r"[（(].*?[）)]", "", _text(acronym)).strip(), _text(full_name)]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return db.resolve(candidate)
        except ValueError:
            pass
    raise ValueError(f"Excel 中的会议无法映射到会议目录：{acronym} / {full_name}")


def import_excel(db, path):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("导入 Excel 需要 openpyxl，请重新安装 requirements-web.txt") from exc

    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Excel 文件不存在：{path}")
    workbook = load_workbook(path, read_only=True, data_only=True)
    missing = {"目标奖项", "作者与单位"}.difference(workbook.sheetnames)
    if missing:
        raise ValueError("Excel 缺少工作表：" + "、".join(sorted(missing)))

    _, award_rows = _rows(workbook["目标奖项"])
    _, author_rows = _rows(workbook["作者与单位"])
    authors_by_record = defaultdict(list)
    for row in author_rows:
        if _text(row.get("所属清单")) == "目标奖项":
            authors_by_record[_text(row.get("记录ID"))].append(row)

    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "coverage": 0, "seeds": 0}
    imported_at = now()
    seen_ids = set()
    conference_by_acronym = {}
    try:
        with db.conn:
            for row in award_rows:
                record_id = _text(row.get("记录ID"))
                if not record_id or record_id in seen_ids:
                    raise ValueError(f"Excel 记录ID为空或重复：{record_id or '[空]'}")
                seen_ids.add(record_id)
                conference = _conference(db, row.get("会议简称"), row.get("会议全称"))
                conference_by_acronym[_text(row.get("会议简称"))] = conference
                year = int(row["会议/颁奖年"])
                award_label = _text(row.get("奖项分类"))
                if award_label not in ("Best Paper Award", "Best Student Paper Award"):
                    raise ValueError(f"记录 {record_id} 的奖项分类不受支持：{award_label}")
                award_type = "best_student_paper" if award_label == "Best Student Paper Award" else "best_paper"
                title = _text(row.get("论文题目"))
                award_url = _url(row.get("官方获奖信息URL"))
                if not title or not award_url:
                    raise ValueError(f"记录 {record_id} 缺少论文题目或官方获奖URL")

                source_urls = [("award", award_url)]
                for value in (row.get("元数据来源URL"), row.get("论文页面URL"), row.get("PDF链接")):
                    url = _url(value)
                    if url and url not in [item[1] for item in source_urls]:
                        source_urls.append(("metadata", url))
                sources = [{"id": f"s{index}", "url": url, "role": role,
                            "text": f"Imported from {path.name}: {title}"}
                           for index, (role, url) in enumerate(source_urls, 1)]

                imported_authors = []
                ordered = sorted(authors_by_record.get(record_id, []), key=lambda item: int(item.get("作者顺序") or 9999))
                for author in ordered:
                    name = _text(author.get("作者姓名"))
                    if not name:
                        continue
                    affiliation = _text(author.get("作者单位"))
                    imported_authors.append({
                        "name": name,
                        "evidence": {"source_id": "s1", "quote": name},
                        "affiliations": ([{"name": affiliation, "evidence": {"source_id": "s1", "quote": affiliation}}]
                                         if affiliation else []),
                    })

                publication_date = _iso_date(row.get("已核实出版时间"), row.get("已核实出版年"))
                date_start, date_end, date_precision = date_bounds(publication_date)
                award_name = _text(row.get("奖项原名")) or award_label
                payload = {
                    "id": record_id, "title": title, "conference_id": conference["id"], "year": year,
                    "award_type": award_type, "award_name": award_name, "track": _text(row.get("赛道")),
                    "authors": imported_authors, "publication_date": publication_date,
                    "date_start": date_start, "date_end": date_end, "date_precision": date_precision,
                    "publication_date_evidence": ({"source_id": "s1", "quote": publication_date} if publication_date else None),
                    "award_evidence": {"source_id": "s1", "quote": f"{award_name}: {title}"},
                    "title_evidence": {"source_id": "s1", "quote": title},
                    "paper_url": _url(row.get("论文页面URL")), "doi": _text(row.get("DOI")) or None,
                    "workbook_source": path.name,
                }
                payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                sources_json = json.dumps(sources, ensure_ascii=False, sort_keys=True)
                old = db.conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
                if old and old["payload"] == payload_json and old["sources"] == sources_json:
                    stats["unchanged"] += 1
                else:
                    if old:
                        db.conn.execute("INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)",
                                        (record_id, json.dumps(dict(old), ensure_ascii=False), imported_at))
                    preserve_review = bool(old and old["reviewer"] and old["reviewer"] != IMPORT_REVIEWER)
                    status = old["status"] if preserve_review else "verified"
                    reviewer = old["reviewer"] if preserve_review else IMPORT_REVIEWER
                    note = old["review_note"] if preserve_review else f"从 {path.name} 导入；官方获奖信息URL已核验。"
                    created = old["created_at"] if old else imported_at
                    db.conn.execute("""INSERT OR REPLACE INTO records
                         (id,conference_id,year,award_type,title,date_start,date_end,status,payload,sources,
                         created_at,updated_at,reviewer,review_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (record_id, conference["id"], year, award_type, title, date_start, date_end, status,
                         payload_json, sources_json, created, imported_at, reviewer, note))
                    stats["updated" if old else "inserted"] += 1
                before = db.conn.total_changes
                db.conn.execute("INSERT OR IGNORE INTO seeds VALUES (?,?,?)", (conference["id"], year, award_url))
                stats["seeds"] += db.conn.total_changes - before

            if "会议年份覆盖" in workbook.sheetnames:
                _, coverage_rows = _rows(workbook["会议年份覆盖"])
                for row in coverage_rows:
                    conference = conference_by_acronym.get(_text(row.get("会议简称"))) or _conference(db, row.get("会议简称"))
                    year = int(row["会议/颁奖年"])
                    evidence_url = next((_url(part.strip()) for part in _text(row.get("已采用的官方来源URL")).split(";") if _url(part.strip())), None)
                    note = _text(row.get("完整性结论")) or _text(row.get("覆盖状态"))
                    for award_type, count_field in (("best_paper", "Best Paper记录数"), ("best_student_paper", "Best Student记录数")):
                        if int(row.get(count_field) or 0) <= 0:
                            continue
                        db.conn.execute("""INSERT INTO coverage VALUES (?,?,?,?,?,?,?)
                            ON CONFLICT(conference_id,year,award_type) DO UPDATE SET state=excluded.state,
                            evidence_url=excluded.evidence_url,note=excluded.note,updated_at=excluded.updated_at""",
                            (conference["id"], year, award_type, "partial", evidence_url, note, imported_at))
                        stats["coverage"] += 1
    finally:
        workbook.close()
    stats["records"] = len(award_rows)
    return stats