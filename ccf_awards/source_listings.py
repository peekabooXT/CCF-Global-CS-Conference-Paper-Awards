"""Aggregate-site listings, separate from official award-event evidence."""

import hashlib
import json

from .model import keytext, norm, url_syntax


# Reviewed on 2026-09-29: identical venue/year and corroborating author lists.
# Keep both original titles in their respective source rows; only identity joins.
_TITLE_VARIANTS = [
    ("CVPR", 2007, "Dynamic 3D Scene Analysis from a Moving Vehicle",
     "Dynamic 3D Scene Analysis from a Moving Vehicles"),
    ("SIGMOD", 2001, "Locally adaptive dimensionality reduction for indexing large time series databases",
     "Locally Adaptive Dimensionality Deduction for Indexing Large Time Series Databases"),
    ("STOC", 2024, "Single-Source Shortest Paths with Negative Real Weights in Õ(mn8/9) Time",
     "Single-Source Shortest Paths with Negative Real Weights in ˜ O (mn8/9) Time"),
    ("OSDI", 2023, "EnsÅ\x8d: A Streaming Interface for NIC-Application Communication",
     "Ensō: A Streaming Interface for NIC-Application Communication"),
    ("SIGMETRICS", 2010, "Load balancing via random local search in closed and open systems",
     "Load Balancing via Randomized Local Search in Closed and Open Systems"),
]
TITLE_ALIASES = {(norm(venue), year, keytext(source)): keytext(existing)
                 for venue, year, source, existing in _TITLE_VARIANTS}


def init_schema(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS source_listings (
      id TEXT PRIMARY KEY, source_name TEXT NOT NULL,
      paper_id TEXT NOT NULL REFERENCES award_papers(id),
      source_venue TEXT NOT NULL, conference_id TEXT REFERENCES conferences(id),
      source_row INTEGER NOT NULL,
      area_raw TEXT, authors_raw TEXT, source_url TEXT NOT NULL,
      discovery_url TEXT, status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL,
      UNIQUE(source_name,paper_id));
    CREATE INDEX IF NOT EXISTS listing_paper_idx ON source_listings(paper_id);
    CREATE TABLE IF NOT EXISTS source_listing_records (
      listing_id TEXT NOT NULL REFERENCES source_listings(id),
      record_id TEXT NOT NULL REFERENCES records(id),
      PRIMARY KEY(listing_id,record_id));
    """)


def _alias_map(conn):
    ids = {}
    contextual = {}
    for row in conn.execute("SELECT id,acronym,data FROM conferences"):
        data = json.loads(row["data"])
        for label in [row["acronym"], *data.get("aliases", [])]:
            ids.setdefault(norm(label), set()).add(row["id"])
        if norm(row["acronym"]) == "fse" and "foundations of software engineering" in norm(data["full_name"]):
            contextual["fse|software engineering"] = row["id"]
    return {**{label: next(iter(values)) for label, values in ids.items() if len(values) == 1},
            **contextual}


def _paper_key(aliases, venue, year, title, area=""):
    label = norm(venue)
    canonical = aliases.get(label + "|" + norm(area), aliases.get(label, label))
    title_key = TITLE_ALIASES.get((label, int(year), keytext(title)), keytext(title))
    return canonical, int(year), title_key


def _paper_id(venue, year, title):
    raw = "\x1f".join((venue, str(year), norm(title)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def import_jeffhuang(conn, document):
    if document.get("format") != "jeffhuang-listings-v1":
        raise ValueError("不是支持的 JeffHuang 收录快照格式")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows 必须是列表")
    status = document.get("review_status", "pending")
    if status not in ("pending", "verified"):
        raise ValueError("未知 JeffHuang 核验状态")
    source_url = url_syntax(document.get("source_url"))
    aliases = _alias_map(conn)
    papers = {}
    for paper in conn.execute("SELECT id,venue,year,title FROM award_papers ORDER BY id"):
        key = _paper_key(aliases, paper["venue"], paper["year"], paper["title"])
        if key in papers and papers[key] != paper["id"]:
            raise ValueError("现有论文存在同一会议、年份、标准化题名的多个 ID；请先人工核对")
        papers[key] = paper["id"]
    records = {}
    for record in conn.execute("SELECT id,conference_id,year,title FROM records WHERE status!='rejected'"):
        key = (record["conference_id"], record["year"], keytext(record["title"]))
        records.setdefault(key, []).append(record["id"])
    event_paper_ids = {r[0] for r in conn.execute("SELECT DISTINCT paper_id FROM award_event_papers")}
    result = {"rows": 0, "inserted_papers": 0, "matched_event_papers": 0,
              "matched_records": 0, "new_candidates": 0}
    seen = set()
    with conn:
        for row in rows:
            venue = str(row["venue"]).strip()
            title = str(row["title"]).strip()
            year = int(row["year"])
            if not venue or not title or not 1900 <= year <= 2200:
                raise ValueError(f"JeffHuang 数据缺少会议、题名或有效年份: {row.get('source_row')}")
            key = _paper_key(aliases, venue, year, title, row.get("area_raw") or "")
            if key in seen:
                raise ValueError(f"JeffHuang 快照内有重复论文: {row.get('source_row')}")
            seen.add(key)
            discovery_url = row.get("discovery_url")
            if discovery_url:
                url_syntax(discovery_url)
            existing_paper = key in papers
            matching_records = records.get(key, [])
            if existing_paper:
                paper_id = papers[key]
            else:
                paper_id = _paper_id(venue, year, title)
                conn.execute("""INSERT OR IGNORE INTO award_papers
                    (id,venue,year,title,authors_raw,paper_url) VALUES (?,?,?,?,?,NULL)""",
                    (paper_id, venue, year, title, row.get("authors_raw")))
                papers[key] = paper_id
                result["inserted_papers"] += 1
            if paper_id in event_paper_ids:
                result["matched_event_papers"] += 1
            if paper_id not in event_paper_ids and not matching_records:
                result["new_candidates"] += 1
            listing_id = "jeffhuang-" + paper_id
            conn.execute("""INSERT INTO source_listings
                (id,source_name,paper_id,source_venue,conference_id,source_row,area_raw,authors_raw,
                 source_url,discovery_url,status,created_at)
                VALUES (?,'jeffhuang',?,?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(id) DO UPDATE SET paper_id=excluded.paper_id,
                source_venue=excluded.source_venue,conference_id=excluded.conference_id,
                source_row=excluded.source_row,
                area_raw=excluded.area_raw,authors_raw=excluded.authors_raw,
                source_url=excluded.source_url,discovery_url=excluded.discovery_url,
                status=CASE WHEN excluded.status='verified' THEN 'verified' ELSE source_listings.status END""",
                (listing_id, paper_id, venue, key[0] if key[0] != norm(venue) else None,
                 int(row["source_row"]), row.get("area_raw"),
                 row.get("authors_raw"), source_url, discovery_url, status))
            for record_id in matching_records:
                conn.execute("INSERT OR IGNORE INTO source_listing_records VALUES (?,?)",
                             (listing_id, record_id))
            if matching_records:
                result["matched_records"] += 1
            result["rows"] += 1
    return result


def list_source_listings(conn, venue="", query="", relation="", limit=50, offset=0):
    if relation not in ("", "event", "record", "new"):
        raise ValueError("未知关联筛选")
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError("分页参数不正确")
    where, args = [], []
    if venue:
        where.append("instr(fold(l.source_venue),?)>0")
        args.append(norm(venue))
    if query:
        where.append("(instr(fold(p.title),?)>0 OR instr(fold(l.authors_raw),?)>0)")
        args.extend([norm(query), norm(query)])
    has_event = "EXISTS (SELECT 1 FROM award_event_papers x WHERE x.paper_id=l.paper_id)"
    has_record = "EXISTS (SELECT 1 FROM source_listing_records z WHERE z.listing_id=l.id)"
    if relation == "event":
        where.append(has_event)
    elif relation == "record":
        where.append(has_record)
    elif relation == "new":
        where.append("NOT " + has_event + " AND NOT " + has_record)
    clause = " WHERE " + " AND ".join(where) if where else ""
    total = conn.execute("SELECT COUNT(*) FROM source_listings l JOIN award_papers p ON p.id=l.paper_id" + clause, args).fetchone()[0]
    sql = """SELECT l.*,p.title,p.year,p.paper_url,c.rank,
      (SELECT COUNT(DISTINCT x.event_id) FROM award_event_papers x WHERE x.paper_id=l.paper_id) AS event_count,
      (SELECT COUNT(*) FROM source_listing_records z WHERE z.listing_id=l.id) AS record_count
      FROM source_listings l JOIN award_papers p ON p.id=l.paper_id
      LEFT JOIN conferences c ON c.id=l.conference_id""" + clause + " ORDER BY p.year DESC,l.source_venue,l.source_row LIMIT ? OFFSET ?"
    return {"total": total, "listings": [dict(r) for r in conn.execute(sql, [*args, limit, offset])]}


def source_listing_detail(conn, listing_id):
    row = conn.execute("""SELECT l.*,p.title,p.year,p.paper_url FROM source_listings l
        JOIN award_papers p ON p.id=l.paper_id WHERE l.id=?""", (listing_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["events"] = [dict(r) for r in conn.execute("""SELECT DISTINCT e.id,e.official_award_name,e.category,e.status
        FROM award_events e JOIN award_event_papers x ON x.event_id=e.id
        WHERE x.paper_id=? ORDER BY e.official_award_name""", (item["paper_id"],))]
    item["records"] = [dict(r) for r in conn.execute("""SELECT r.id,r.award_type,r.status
        FROM records r JOIN source_listing_records z ON z.record_id=r.id
        WHERE z.listing_id=? ORDER BY r.id""", (listing_id,))]
    return item
