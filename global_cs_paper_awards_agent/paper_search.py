"""Search legacy records and verified award-event papers together."""

import json

from .model import norm
from .ontology import CATEGORIES, classify_award


def paper_provenance(conn, record_id, verified_only=True):
    """Read linked listings on demand, without changing paper or award identity."""
    record_id = str(record_id)
    paper_ids = []
    core_id = None
    if record_id.startswith("event:"):
        parts = record_id.split(":")
        if len(parts) != 3:
            return None
        sql = """SELECT x.paper_id FROM award_event_papers x JOIN award_events e ON e.id=x.event_id
            WHERE x.event_id=? AND x.paper_id=?"""
        if verified_only:
            sql += " AND x.status='verified' AND e.status='verified'"
        row = conn.execute(sql, parts[1:]).fetchone()
        if row is None:
            return None
        paper_ids.append(row["paper_id"])
    elif record_id.startswith("listing:"):
        sql = "SELECT paper_id FROM source_listings WHERE id=?"
        if verified_only:
            sql += " AND status='verified'"
        row = conn.execute(sql, (record_id[len("listing:"):],)).fetchone()
        if row is None:
            return None
        paper_ids.append(row["paper_id"])
    else:
        sql = "SELECT id FROM records WHERE id=?"
        if verified_only:
            sql += " AND status='verified'"
        row = conn.execute(sql, (record_id,)).fetchone()
        if row is None:
            return None
        core_id = row["id"]

    if core_id is not None:
        condition = "EXISTS (SELECT 1 FROM source_listing_records z WHERE z.listing_id=l.id AND z.record_id=?)"
        args = [core_id]
    else:
        condition = "l.paper_id IN (" + ",".join("?" for _ in paper_ids) + ")"
        args = paper_ids
    sql = """SELECT l.*,p.title,p.year FROM source_listings l
        JOIN award_papers p ON p.id=l.paper_id WHERE """ + condition
    if verified_only:
        sql += " AND l.status='verified'"
    listings = []
    for row in conn.execute(sql + " ORDER BY l.source_name,l.source_row,l.id", args):
        item = {key: row[key] for key in (
            "id", "source_name", "source_venue", "source_row", "source_url", "discovery_url",
            "status", "area_raw", "authors_raw", "title", "year")}
        event_sql = """SELECT DISTINCT e.id,e.official_award_name,e.venue,e.year,e.status
            FROM award_events e JOIN award_event_papers x ON x.event_id=e.id WHERE x.paper_id=?"""
        if verified_only:
            event_sql += " AND e.status='verified' AND x.status='verified'"
        item["linked_awards"] = [dict(r) for r in conn.execute(
            event_sql + " ORDER BY e.year DESC,e.official_award_name", (row["paper_id"],))]
        count_sql = """SELECT COUNT(DISTINCT r.id) FROM source_listing_records z
            JOIN records r ON r.id=z.record_id WHERE z.listing_id=?"""
        if verified_only:
            count_sql += " AND r.status='verified'"
        item["linked_record_count"] = conn.execute(count_sql, (row["id"],)).fetchone()[0]
        listings.append(item)
    return {"record_id": record_id, "listings": listings}


def award_names(conn):
    """Return original award names, not the two legacy internal award types."""
    names = {row[0] for row in conn.execute(
        "SELECT DISTINCT official_award_name FROM award_events"
    ) if row[0]}
    for row in conn.execute("SELECT payload FROM records WHERE status!='rejected'"):
        name = json.loads(row[0]).get("award_name")
        if name:
            names.add(name)
    return sorted(names, key=norm)


def search_papers(db, filters):
    """Search all paper sources with one broad category per returned item."""
    filters = dict(filters)
    award_name = filters.pop("award_name", None)
    category = filters.pop("category", None)
    if category and category not in CATEGORIES:
        raise ValueError("未知奖项分类")
    legacy_award = filters.get("award")
    core = db.search(**filters)
    if award_name:
        core = [row for row in core if norm(row.get("award_name", "")) == norm(award_name)]
    for row in core:
        row.update(classify_award(row.get("award_name")))
    if category:
        core = [row for row in core if row["category"] == category]
    seen = {(norm(row["acronym"]), row["year"], norm(row["title"]),
             norm(row.get("award_name", ""))) for row in core}
    if legacy_award:
        return core

    where, args = [], []
    for column, value, operator in (
        ("e.conference_id", filters.get("conference"), "="),
        ("c.rank", filters.get("rank"), "="),
        ("e.year", filters.get("year_from"), ">="),
        ("e.year", filters.get("year_to"), "<="),
    ):
        if value is not None:
            where.append(f"{column} {operator} ?")
            args.append(value)
    status = filters.get("status", "active")
    if status not in ("active", "all"):
        if status == "rejected":
            return core
        where.append("x.status=?")
        args.append(status)
    if filters.get("title"):
        where.append("instr(fold(p.title),?)>0")
        args.append(norm(filters["title"]))
    if filters.get("author"):
        where.append("instr(fold(COALESCE(p.authors_raw,'')),?)>0")
        args.append(norm(filters["author"]))
    if award_name:
        where.append("fold(e.official_award_name)=?")
        args.append(norm(award_name))
    # EviDOM annotations do not contain structured author affiliations or
    # publication dates. They cannot truthfully satisfy those filters.
    if filters.get("affiliation") or filters.get("published_from") or filters.get("published_to"):
        return core
    sql = """SELECT x.annotation_id,x.event_id,x.source_url,x.evidence,x.note,x.status,
        e.venue,e.year,e.official_award_name,e.category,e.student_only,
        p.id AS paper_id,p.title,p.authors_raw,p.paper_url,
        c.acronym,c.rank,c.area
        FROM award_event_papers x
        JOIN award_events e ON e.id=x.event_id
        JOIN award_papers p ON p.id=x.paper_id
        LEFT JOIN conferences c ON c.id=e.conference_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY e.year DESC,fold(e.venue),fold(p.title),fold(e.official_award_name)"
    event_rows = {}
    for row in db.conn.execute(sql, args):
        label = classify_award(row["official_award_name"])
        if category and label["category"] != category:
            continue
        key = (row["event_id"], row["paper_id"])
        if key in event_rows:
            existing = event_rows[key]
            if not any(source["url"] == row["source_url"] for source in existing["sources"]):
                existing["sources"].append({"id": row["annotation_id"], "role": "award", "url": row["source_url"]})
            existing["evidence"].extend(json.loads(row["evidence"]))
            continue
        acronym = row["acronym"] or row["venue"]
        identity = (norm(acronym), row["year"], norm(row["title"]), norm(row["official_award_name"]))
        if identity in seen:
            continue
        seen.add(identity)
        event_rows[key] = {
            "id": "event:" + row["event_id"] + ":" + row["paper_id"],
            "source_kind": "award_event", "event_id": row["event_id"],
            "title": row["title"], "acronym": acronym, "rank": row["rank"],
            "area": row["area"], "year": row["year"],
            "award_name": row["official_award_name"], "award_type": label["category"],
            "category": label["category"], "category_label": label["category_label"],
            "student_only": label["student_only"], "status": row["status"],
            "authors": [], "authors_raw": row["authors_raw"],
            "publication_date": None, "date_precision": "unknown",
            "paper_url": row["paper_url"], "doi": None,
            "sources": [{"id": row["annotation_id"], "role": "award", "url": row["source_url"]}],
            "evidence": json.loads(row["evidence"]), "note": row["note"],
        }
    listings = []
    if category in (None, "paper") and not award_name and not legacy_award and not (
            filters.get("affiliation") or filters.get("published_from") or filters.get("published_to")):
        listing_where, listing_args = [
            "NOT EXISTS (SELECT 1 FROM award_event_papers x WHERE x.paper_id=l.paper_id)",
            "NOT EXISTS (SELECT 1 FROM source_listing_records z WHERE z.listing_id=l.id)",
        ], []
        for column, value, operator in (
            ("l.conference_id", filters.get("conference"), "="),
            ("c.rank", filters.get("rank"), "="),
            ("p.year", filters.get("year_from"), ">="),
            ("p.year", filters.get("year_to"), "<="),
        ):
            if value is not None:
                listing_where.append(f"{column} {operator} ?")
                listing_args.append(value)
        if status == "rejected":
            listing_where.append("1=0")
        elif status not in ("active", "all"):
            listing_where.append("l.status=?")
            listing_args.append(status)
        if filters.get("title"):
            listing_where.append("instr(fold(p.title),?)>0")
            listing_args.append(norm(filters["title"]))
        if filters.get("author"):
            listing_where.append("instr(fold(COALESCE(l.authors_raw,'')),?)>0")
            listing_args.append(norm(filters["author"]))
        listing_sql = """SELECT l.id,l.paper_id,l.source_venue,l.authors_raw,l.source_url,l.status,
            p.title,p.year,p.paper_url,c.acronym,c.rank,c.area
            FROM source_listings l JOIN award_papers p ON p.id=l.paper_id
            LEFT JOIN conferences c ON c.id=l.conference_id
            WHERE """ + " AND ".join(listing_where)
        listing_papers = set()
        for row in db.conn.execute(listing_sql, listing_args):
            if row["paper_id"] in listing_papers:
                continue
            listing_papers.add(row["paper_id"])
            listings.append({
                "id": "listing:" + row["id"], "source_kind": "source_listing",
                "title": row["title"], "acronym": row["acronym"] or row["source_venue"],
                "rank": row["rank"], "area": row["area"], "year": row["year"],
                "award_name": None, "award_type": "paper", "category": "paper",
                "category_label": CATEGORIES["paper"], "student_only": False,
                "status": row["status"], "authors": [], "authors_raw": row["authors_raw"],
                "publication_date": None, "date_precision": "unknown",
                "paper_url": row["paper_url"], "doi": None,
                "sources": [{"id": row["id"], "role": "listing", "url": row["source_url"]}],
            })
    return sorted([*core, *event_rows.values(), *listings], key=lambda row: (
        -row["year"], norm(row["acronym"]), norm(row["title"]), norm(row.get("award_name") or "")))
