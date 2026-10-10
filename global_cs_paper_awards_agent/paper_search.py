"""Search legacy records and verified award-event papers together."""

import json
from collections import defaultdict
from urllib.parse import urlsplit

from .model import norm
from .ontology import CATEGORIES, classify_award


def title_identity(value):
    """Conservative identity: typography only, never fuzzy title matching."""
    return norm(value).translate(str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"'}))


def conference_aliases(conn):
    names = defaultdict(set)
    for row in conn.execute('SELECT id,acronym,data FROM conferences'):
        for label in [row['acronym'], *json.loads(row['data']).get('aliases', [])]:
            names[norm(label)].add(row['id'])
    return {name: next(iter(ids)) for name, ids in names.items() if len(ids) == 1}


def paper_identity(aliases, venue, year, title):
    return aliases.get(norm(venue), norm(venue)), int(year), title_identity(title)


def merge_paper_results(rows, aliases=None):
    """One paper per result; retain every award and evidence, not extra rows."""
    groups = defaultdict(list)
    for row in rows:
        groups[paper_identity(aliases or {}, row['acronym'], row['year'], row['title'])].append(row)
    merged = []
    for members in groups.values():
        primary = next((r for r in members if r.get('authors')), members[0])
        item = dict(primary)
        item['related_record_ids'] = list(dict.fromkeys(r['id'] for r in members))
        item['awards'] = []
        seen_awards = set()
        for member in members:
            name = member.get('award_name')
            key = title_identity(name or '')
            if name and key not in seen_awards:
                seen_awards.add(key)
                item['awards'].append({k: member.get(k) for k in (
                    'id', 'event_id', 'award_name', 'category', 'category_label', 'status')})
        item['award_name'] = '；'.join(a['award_name'] for a in item['awards']) or None
        item['categories'] = list(dict.fromkeys(r['category'] for r in members))
        item['category_labels'] = list(dict.fromkeys(r['category_label'] for r in members))
        item['category_label'] = ' / '.join(item['category_labels'])
        item['sources'] = list({(s.get('id'), s.get('url')): s for r in members for s in r.get('sources', [])}.values())
        item['evidence'] = [e for r in members for e in r.get('evidence', [])]
        for field in ('paper_url', 'doi', 'discovery_url', 'authors_raw', 'publication_date'):
            if field == 'discovery_url' and not any(r.get(field) for r in members):
                continue
            item[field] = next((r[field] for r in members if r.get(field)), item.get(field))
        merged.append(item)
    return sorted(merged, key=lambda r: (-r['year'], norm(r['acronym']), norm(r['title'])))


def _record_provenance(conn, record_id, verified_only=True):
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


def _with_discovery_urls(conn, rows):
    """Attach verified, saved Scholar links in two batched reads, without changing data."""
    by_paper, by_listing, by_record = {}, {}, {}
    for row in conn.execute("""SELECT id,paper_id,discovery_url FROM source_listings
        WHERE status='verified' AND discovery_url IS NOT NULL ORDER BY source_name,source_row,id"""):
        try:
            url = urlsplit(row['discovery_url'])
            if (url.scheme != 'https' or url.hostname not in {'scholar.google.com', 'scholar.google.com.hk'}
                    or url.path != '/scholar' or url.username or url.password or url.port not in (None, 443)):
                continue
        except ValueError:
            continue
        by_listing[row['id']] = row['discovery_url']
        by_paper.setdefault(row['paper_id'], row['discovery_url'])
    for row in conn.execute('SELECT listing_id,record_id FROM source_listing_records ORDER BY listing_id,record_id'):
        if row['listing_id'] in by_listing:
            by_record.setdefault(row['record_id'], by_listing[row['listing_id']])
    for row in rows:
        identifier = row['id']
        if identifier.startswith('event:'):
            address = by_paper.get(identifier.rsplit(':', 1)[-1])
        elif identifier.startswith('listing:'):
            address = by_listing.get(identifier[len('listing:'):])
        else:
            address = by_record.get(identifier)
        if address:
            row['discovery_url'] = address
    return rows


def search_paper_records(db, filters):
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
        return _with_discovery_urls(db.conn, core)

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
    if status == 'active':
        where.append("x.status!='rejected'")
    if status not in ("active", "all"):
        if status == "rejected":
            return _with_discovery_urls(db.conn, core)
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
        return _with_discovery_urls(db.conn, core)
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
        elif status == 'active':
            listing_where.append("l.status!='rejected'")
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
    return _with_discovery_urls(db.conn, sorted([*core, *event_rows.values(), *listings], key=lambda row: (
        -row["year"], norm(row["acronym"]), norm(row["title"]), norm(row.get("award_name") or ""))))


def search_papers(db, filters):
    return merge_paper_results(search_paper_records(db, filters), conference_aliases(db.conn))


def paper_provenance(conn, record_id, verified_only=True):
    original = _record_provenance(conn, record_id, verified_only)
    if original is None:
        return None
    # Reuse the same result identity to include provenance from every linked row.
    class View:
        def __init__(self, connection):
            self.conn = connection
        def search(self, **filters):
            if verified_only:
                from .public_db import Database
            else:
                from .db import Database
            view = object.__new__(Database)
            view.conn = self.conn
            return view.search(**filters)
    rows = search_papers(View(conn), {'status': 'verified' if verified_only else 'all'})
    paper = next((r for r in rows if record_id in r['related_record_ids']), None)
    if paper:
        listings = {r['id']: r for identifier in paper['related_record_ids']
                    for r in (_record_provenance(conn, identifier, verified_only) or {}).get('listings', [])}
        original['listings'] = list(listings.values())
        original['awards'] = paper['awards']
    return original
