"""Award events and lossless EviDOM annotations.

The annotation corpus is separate from the verified ``records`` table.  In
particular, importing it cannot silently change coverage or review decisions.
"""

import hashlib
import json
import re

from .model import norm
from .ontology import CATEGORIES, classify_award


PAGE_VENUES = {
    "0003": "SIGMETRICS", "0004": "AAAI", "0006": "CVPR", "0008": "ICML",
    "0012": "AAAI", "0015": "SIGMOD", "0018": "SIGMOD", "0019": "SIGMOD",
    "0020": "SIGMOD", "0022": "NeurIPS", "0023": "NeurIPS", "0024": "ICCV",
    "0025": "PODS", "0026": "SIGIR", "0027": "SIGMOD", "0028": "SIGIR",
    "0029": "ICCV", "0030": "SIGCOMM", "0034": "KDD", "0035": "SIGMOD",
    "0036": "KDD", "0040": "KDD", "0041": "KDD", "0042": "KDD",
    "0043": "KDD", "0044": "KDD", "0054": "SIGCOMM", "0059": "ICFP",
    "0060": "OOPSLA", "0067": "VLDB", "0082": "SIGIR", "0083": "SIGIR",
    "0108": "KDD",
}
USENIX_PAGES = {"0005", "0009", "0010", "0013", "0014", "0016", "0017", "0021", "0031"}


def venue_for(page_id, award_name):
    number = (page_id or "").removeprefix("page-")
    if number in USENIX_PAGES:
        # The USENIX index mixes independent conferences; the suffix is part
        # of the annotator's original award label, not a page-wide venue.
        match = re.search(r"/\s*(.+?)\s*(?:'\d{2}|20\d{2})\s*$", award_name or "")
        return match.group(1).strip() if match else "USENIX (未细分)"
    return PAGE_VENUES.get(number, "未映射")


def _id(*parts):
    return hashlib.sha256("\x1f".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:24]


def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS award_events (
      id TEXT PRIMARY KEY, venue TEXT NOT NULL, conference_id TEXT,
      year INTEGER NOT NULL, official_award_name TEXT NOT NULL,
      category TEXT NOT NULL, student_only INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
      FOREIGN KEY(conference_id) REFERENCES conferences(id));
    CREATE INDEX IF NOT EXISTS event_filter_idx ON award_events(venue,year,category);
    CREATE TABLE IF NOT EXISTS award_papers (
      id TEXT PRIMARY KEY, venue TEXT NOT NULL, year INTEGER NOT NULL,
      title TEXT NOT NULL, authors_raw TEXT, paper_url TEXT);
    CREATE TABLE IF NOT EXISTS award_event_papers (
      annotation_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES award_events(id),
      paper_id TEXT NOT NULL REFERENCES award_papers(id), source_url TEXT NOT NULL,
      source_page_id TEXT NOT NULL, evidence TEXT NOT NULL, note TEXT,
      status TEXT NOT NULL DEFAULT 'pending');
    CREATE INDEX IF NOT EXISTS event_paper_event_idx ON award_event_papers(event_id);
    """)


def import_annotations(conn, document):
    if document.get("format") != "evidom-award-annotations-v1":
        raise ValueError("不是支持的 EviDOM 标注导出格式")
    rows = document.get("records")
    if not isinstance(rows, list):
        raise ValueError("records 必须是列表")
    status = document.get("review_status", "pending")
    if status not in ("pending", "verified"):
        raise ValueError("未知 EviDOM 核验状态")
    aliases = {}
    for cid, acronym, rank, data in conn.execute("SELECT id,acronym,rank,data FROM conferences"):
        for label in [acronym, *json.loads(data).get("aliases", [])]:
            aliases.setdefault(norm(label), set()).add(cid)
    catalog = {label: next(iter(ids)) for label, ids in aliases.items() if len(ids) == 1}
    events, papers = set(), set()
    with conn:
        for row in rows:
            annotation_id = str(row["annotation_id"])
            venue = venue_for(row["page_id"], row["official_award_name"])
            year = int(row["year"])
            if not 1900 <= year <= 2200:
                raise ValueError(f"无效获奖年份: {annotation_id}")
            name = str(row["official_award_name"]).strip()
            title = str(row["title"]).strip()
            source_url = str(row["source_url"]).strip()
            if not (name and title and source_url.startswith(("http://", "https://"))):
                raise ValueError(f"缺少奖项、题名或来源: {annotation_id}")
            ontology = classify_award(name)
            event_id = _id(venue, year, norm(name))
            paper_id = _id(venue, year, norm(title))
            cid = catalog.get(norm(venue))
            conn.execute("""INSERT INTO award_events
                VALUES (?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                conference_id=COALESCE(excluded.conference_id,award_events.conference_id),
                status=CASE WHEN excluded.status='verified' THEN 'verified' ELSE award_events.status END""",
                (event_id, venue, cid, year, name, ontology["category"], int(ontology["student_only"]), status))
            conn.execute("""INSERT INTO award_papers VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                authors_raw=COALESCE(NULLIF(excluded.authors_raw,''),award_papers.authors_raw),
                paper_url=COALESCE(NULLIF(excluded.paper_url,''),award_papers.paper_url)""",
                (paper_id, venue, year, title, row.get("authors_raw"), row.get("paper_url")))
            conn.execute("""INSERT INTO award_event_papers VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(annotation_id) DO UPDATE SET event_id=excluded.event_id,
                paper_id=excluded.paper_id,source_url=excluded.source_url,
                source_page_id=excluded.source_page_id,evidence=excluded.evidence,
                note=excluded.note,
                status=CASE WHEN excluded.status='verified' THEN 'verified' ELSE award_event_papers.status END""",
                (annotation_id, event_id, paper_id, source_url, row["page_id"],
                 json.dumps(row.get("evidence", []), ensure_ascii=False), row.get("note"), status))
            events.add(event_id)
            papers.add(paper_id)
    return {"annotations": len(rows), "events": len(events), "papers": len(papers),
            "unmapped_venues": conn.execute("SELECT COUNT(*) FROM award_events WHERE conference_id IS NULL").fetchone()[0]}


def list_events(conn, venue="", category="", query="", limit=100, offset=0):
    if category and category not in CATEGORIES:
        raise ValueError("未知奖项分类")
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("分页参数不正确")
    clauses, args = [], []
    if venue:
        clauses.append("instr(fold(e.venue),?)>0")
        args.append(norm(venue))
    if category:
        clauses.append("e.category=?")
        args.append(category)
    if query:
        clauses.append("(instr(fold(e.official_award_name),?)>0 OR EXISTS (SELECT 1 FROM award_event_papers x JOIN award_papers p ON p.id=x.paper_id WHERE x.event_id=e.id AND instr(fold(p.title),?)>0))")
        args.extend([norm(query), norm(query)])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = conn.execute("SELECT COUNT(*) FROM award_events e" + where, args).fetchone()[0]
    sql = """SELECT e.*,c.rank,COUNT(x.annotation_id) AS annotation_count,
      COUNT(DISTINCT x.paper_id) AS paper_count FROM award_events e
      LEFT JOIN conferences c ON c.id=e.conference_id
      LEFT JOIN award_event_papers x ON x.event_id=e.id""" + where + " GROUP BY e.id ORDER BY e.year DESC,e.venue,e.official_award_name LIMIT ? OFFSET ?"
    rows = [dict(r) for r in conn.execute(sql, [*args, limit, offset])]
    for event in rows:
        event["category_label"] = CATEGORIES[event["category"]]
    return {"total": total, "events": rows}


def event_detail(conn, event_id):
    row = conn.execute("SELECT e.*,c.rank FROM award_events e LEFT JOIN conferences c ON c.id=e.conference_id WHERE e.id=?", (event_id,)).fetchone()
    if not row:
        return None
    event = dict(row)
    event["category_label"] = CATEGORIES[event["category"]]
    event["papers"] = []
    for r in conn.execute("""SELECT p.*,x.annotation_id,x.source_url,x.source_page_id,x.evidence,x.note,x.status
        FROM award_event_papers x JOIN award_papers p ON p.id=x.paper_id
        WHERE x.event_id=? ORDER BY p.title,x.annotation_id""", (event_id,)):
        paper = dict(r)
        paper["evidence"] = json.loads(paper["evidence"])
        event["papers"].append(paper)
    return event
