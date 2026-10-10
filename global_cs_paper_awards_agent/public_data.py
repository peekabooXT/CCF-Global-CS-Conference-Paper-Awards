"""Reviewed publication data, independent of local collection and run history."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .model import norm, validate_bundle, url_syntax
from .ontology import classify_award
from .paper_search import conference_aliases, paper_identity

PUBLIC_TABLES = ("conferences", "records", "award_events", "award_papers",
                 "award_event_papers", "source_listings", "source_listing_records")
REVIEW_TABLES = ("records", "award_events", "award_papers", "award_event_papers",
                 "source_listings", "source_listing_records")


def publication_time():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]


def review_preview(db):
    tables = {table: _rows(db.conn, table) for table in REVIEW_TABLES}
    digest = hashlib.sha256(json.dumps(tables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    pending = {"records": 0, "event_papers": 0, "source_listings": 0}
    errors = []
    for row in tables["records"]:
        if row["status"] != "pending":
            continue
        pending["records"] += 1
        try:
            valid, rejected = validate_bundle({"conference_id": row["conference_id"], "year": row["year"],
                "sources": json.loads(row["sources"]), "records": [json.loads(row["payload"])]},
                row["conference_id"], row["year"])
            if rejected or not valid:
                raise ValueError(rejected[0]["error"] if rejected else "缺少有效论文")
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"id": row["id"], "title": row["title"], "reason": str(exc)})
    for table, key, source_field in (("award_event_papers", "event_papers", "source_url"),
                                      ("source_listings", "source_listings", "source_url")):
        for row in tables[table]:
            if row["status"] != "pending":
                continue
            pending[key] += 1
            try:
                url_syntax(row[source_field])
                if table == "award_event_papers" and not json.loads(row["evidence"]):
                    raise ValueError("获奖关联缺少证据片段，请先逐条核对或排除")
            except (ValueError, TypeError) as exc:
                errors.append({"id": row.get("annotation_id", row.get("id")), "reason": str(exc)})
    verified = {table: sum(row.get("status") == "verified" for row in tables[table])
                for table in ("records", "award_event_papers", "source_listings")}
    return {"digest": digest, "pending": pending, "pending_total": sum(pending.values()),
            "verified": verified, "errors": errors}


def confirm_review(db, expected_digest, reviewer, note):
    reviewer = str(reviewer or "").strip()
    if not reviewer:
        raise ValueError("请填写审核人")
    preview = review_preview(db)
    if preview["digest"] != expected_digest:
        raise ValueError("待审核数据已经变化，请重新打开预览再确认")
    if preview["errors"]:
        raise ValueError("部分待审核数据缺少有效证据，请先处理预览中的问题")
    stamp = publication_time()
    for row in db.conn.execute("SELECT * FROM records WHERE status='pending'").fetchall():
        db.conn.execute("INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)",
                        (row["id"], json.dumps(dict(row), ensure_ascii=False), stamp))
    db.conn.execute("UPDATE records SET status='verified',reviewer=?,review_note=?,updated_at=? WHERE status='pending'",
                    (reviewer, note, stamp))
    db.conn.execute("UPDATE award_event_papers SET status='verified',note=COALESCE(note,'') || ? WHERE status='pending'",
                    (f"\n审核：{reviewer}；{stamp}；{note}",))
    db.conn.execute("UPDATE source_listings SET status='verified' WHERE status='pending'")
    db.conn.execute("""UPDATE award_events SET status='verified' WHERE EXISTS
        (SELECT 1 FROM award_event_papers x WHERE x.event_id=award_events.id AND x.status='verified')""")
    return preview["pending"]


def _id(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:24]


def public_snapshot(db, published_at=None, release_id=None):
    """Whitelist verified public rows and derive award events for collected records."""
    tables = {"conferences": _rows(db.conn, "conferences")}
    tables["records"] = [r for r in _rows(db.conn, "records") if r["status"] == "verified"]
    for row in tables['records']:
        row['reviewer'] = row['review_note'] = None
    links = [r for r in _rows(db.conn, "award_event_papers") if r["status"] == "verified"]
    for row in links:
        row['note'] = None
    event_ids = {r["event_id"] for r in links}
    events = {r["id"]: {**r, "status": "verified"} for r in _rows(db.conn, "award_events") if r["id"] in event_ids}
    listings = [r for r in _rows(db.conn, "source_listings") if r["status"] == "verified"]
    paper_ids = {r["paper_id"] for r in [*links, *listings]}
    papers = {r["id"]: r for r in _rows(db.conn, "award_papers") if r["id"] in paper_ids}
    aliases = conference_aliases(db.conn)
    paper_keys = {paper_identity(aliases,r['venue'],r['year'],r['title']):r['id'] for r in papers.values()}
    event_keys = {(norm(r["venue"]), r["year"], norm(r["official_award_name"])): r["id"] for r in events.values()}
    conference_map = {r["id"]: r for r in tables["conferences"]}
    for row in tables["records"]:
        record = json.loads(row["payload"])
        venue = conference_map[row["conference_id"]]["acronym"]
        name = record.get("award_name") or "来源未提供奖项原名"
        event_key = (norm(venue), row["year"], norm(name))
        event_id = event_keys.setdefault(event_key, _id(venue, row["year"], norm(name)))
        label = classify_award(name)
        events.setdefault(event_id, {"id": event_id, "venue": venue, "conference_id": row["conference_id"],
            "year": row["year"], "official_award_name": name, "category": label["category"],
            "student_only": int(label["student_only"]), "status": "verified", "created_at": row["created_at"]})
        paper_key = paper_identity(aliases,venue,row['year'],row['title'])
        paper_id = paper_keys.setdefault(paper_key, _id(venue, row["year"], norm(row["title"])))
        papers.setdefault(paper_id, {"id": paper_id, "venue": venue, "year": row["year"], "title": row["title"],
            "authors_raw": "; ".join(a["name"] for a in record.get("authors", [])), "paper_url": record.get("paper_url")})
        if not any(x["event_id"] == event_id and x["paper_id"] == paper_id for x in links):
            evidence = record.get("award_evidence") or {}
            source = next((s for s in json.loads(row["sources"]) if s["id"] == evidence.get("source_id")), None)
            if source is None:
                raise ValueError(f"已核验论文缺少奖项来源：{row['title']}")
            links.append({"annotation_id": "record:" + row["id"], "event_id": event_id, "paper_id": paper_id,
                "source_url": source["url"], "source_page_id": source["id"],
                "evidence": json.dumps([evidence], ensure_ascii=False), "note": row["review_note"], "status": "verified"})
    tables.update(award_events=list(events.values()), award_papers=list(papers.values()),
                  award_event_papers=links, source_listings=listings)
    listing_ids = {r["id"] for r in listings}
    record_ids = {r["id"] for r in tables["records"]}
    tables["source_listing_records"] = [r for r in _rows(db.conn, "source_listing_records")
                                        if r["listing_id"] in listing_ids and r["record_id"] in record_ids]
    schema = {table: db.conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
              for table in PUBLIC_TABLES}
    return {"schema_version": 2, "publication": {"release_id": release_id or uuid.uuid4().hex,
            "published_at": published_at or publication_time(), "timezone": "Asia/Shanghai",
            "counts": {table: len(tables[table]) for table in PUBLIC_TABLES if table != "conferences"}},
            "schema": schema, "tables": tables}


def write_public_database(snapshot, path):
    path = Path(path)
    if path.exists():
        raise ValueError("公开数据库目标已存在，不能覆盖现有文件")
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        for table in PUBLIC_TABLES:
            conn.execute(snapshot["schema"][table])
            for row in snapshot["tables"][table]:
                columns = list(row)
                if any(not c.replace("_", "").isalnum() for c in columns):
                    raise ValueError("无效数据库字段")
                conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                             [row[c] for c in columns])
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("公开数据库完整性校验失败")
        conn.commit()
