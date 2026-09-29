"""Search legacy records and verified award-event papers together."""

import json

from .model import norm


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
    """Keep rich core records and add distinct event-paper links without inventing metadata."""
    filters = dict(filters)
    award_name = filters.pop("award_name", None)
    legacy_award = filters.get("award")
    core = db.search(**filters)
    if award_name:
        core = [row for row in core if norm(row.get("award_name", "")) == norm(award_name)]
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
            "award_name": row["official_award_name"], "award_type": row["category"],
            "student_only": bool(row["student_only"]), "status": row["status"],
            "authors": [], "authors_raw": row["authors_raw"],
            "publication_date": None, "date_precision": "unknown",
            "paper_url": row["paper_url"], "doi": None,
            "sources": [{"id": row["annotation_id"], "role": "award", "url": row["source_url"]}],
            "evidence": json.loads(row["evidence"]), "note": row["note"],
        }
    return sorted([*core, *event_rows.values()], key=lambda row: (
        -row["year"], norm(row["acronym"]), norm(row["title"]), norm(row.get("award_name", ""))))
