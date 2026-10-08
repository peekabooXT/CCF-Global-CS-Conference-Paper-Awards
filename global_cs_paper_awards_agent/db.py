import datetime as dt
import json
import sqlite3
from pathlib import Path
from .catalog import load_catalog
from .model import norm, now, validate_bundle

_UNSET = object()


class Database:
    def __init__(self, path, read_only=False):
        if read_only:
            self.conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function("fold", 1, lambda x: norm(x or ""), deterministic=True)
        self.conn.execute("PRAGMA foreign_keys=ON")
        if read_only:
            self.conn.execute("PRAGMA query_only=ON")
            return
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS conferences (
          id TEXT PRIMARY KEY, acronym TEXT NOT NULL, rank TEXT NOT NULL,
          area TEXT NOT NULL, full_name TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS seeds (
          conference_id TEXT REFERENCES conferences(id), year INTEGER,
          url TEXT NOT NULL, PRIMARY KEY(conference_id,year,url));
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, conference_id TEXT REFERENCES conferences(id),
          year INTEGER NOT NULL, award_type TEXT NOT NULL, title TEXT NOT NULL,
          date_start TEXT, date_end TEXT, status TEXT NOT NULL,
          payload TEXT NOT NULL, sources TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          reviewer TEXT, review_note TEXT);
        CREATE INDEX IF NOT EXISTS search_idx ON records(conference_id,year,award_type);
        CREATE TABLE IF NOT EXISTS revisions (
          id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, snapshot TEXT NOT NULL,
          archived_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS coverage (
          conference_id TEXT REFERENCES conferences(id), year INTEGER,
          award_type TEXT, state TEXT NOT NULL, evidence_url TEXT, note TEXT,
          updated_at TEXT, PRIMARY KEY(conference_id,year,award_type));
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, conference_id TEXT REFERENCES conferences(id),
          year INTEGER, started_at TEXT, finished_at TEXT, status TEXT, details TEXT);
        """)
        if "deleted_at" not in {row[1] for row in self.conn.execute("PRAGMA table_info(runs)")}:
            self.conn.execute("ALTER TABLE runs ADD COLUMN deleted_at TEXT")
        if "expected_count" not in {row[1] for row in self.conn.execute("PRAGMA table_info(coverage)")}:
            self.conn.execute("ALTER TABLE coverage ADD COLUMN expected_count INTEGER")
            self.conn.execute("UPDATE coverage SET expected_count=0 WHERE state='not_offered'")
        from .award_events import init_schema
        init_schema(self.conn)
        from .source_listings import init_schema as init_source_listings
        init_source_listings(self.conn)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def init(self, rows=None):
        rows = rows or load_catalog()
        with self.conn:
            for r in rows:
                self.conn.execute("""INSERT INTO conferences VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET acronym=excluded.acronym,
                rank=excluded.rank,area=excluded.area,full_name=excluded.full_name,data=excluded.data""",
                (r["id"], r["acronym"], r["rank"], r["area"], r["full_name"], json.dumps(r, ensure_ascii=False)))
        return len(rows)

    def conferences(self, query="", rank=None):
        rows = [json.loads(r[0]) for r in self.conn.execute("SELECT data FROM conferences ORDER BY area,rank,acronym")]
        return [r for r in rows if (not rank or r["rank"] == rank) and
                (not query or norm(query) in norm(json.dumps(r, ensure_ascii=False)))]

    def resolve(self, value):
        rows = self.conferences()
        exact = [r for r in rows if value == r["id"]]
        if exact:
            return exact[0]
        matches = [r for r in rows if norm(value) in [norm(r["acronym"]), norm(r["full_name"]),
                                                    *[norm(a) for a in r["aliases"]]]]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            options = "；".join(f'{r["id"]} ({r["area"]}, {r["full_name"]})' for r in matches)
            raise ValueError("会议简称有歧义，请使用编号：" + options)
        raise ValueError("没有找到会议，请先 init 并用 conferences --query 查找")

    def add_seed(self, cid, year, url):
        from .model import url_syntax
        url_syntax(url)
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO seeds VALUES (?,?,?)", (cid, year, url))

    def replace_seeds(self, cid, year, expected_urls, urls):
        """Replace one conference-year's URLs only if the reviewed snapshot is current."""
        from .model import url_syntax
        if type(year) is not int or not 1900 <= year <= 2200:
            raise ValueError("年份必须在 1900–2200 之间")
        if not self.conn.execute("SELECT 1 FROM conferences WHERE id=?", (cid,)).fetchone():
            raise ValueError("会议不存在")
        if not isinstance(expected_urls, list) or not isinstance(urls, list) or len(expected_urls) > 100 or not 0 < len(urls) <= 100:
            raise ValueError("网址列表无效或超过 100 条")
        if any(not isinstance(url, str) for url in [*expected_urls, *urls]):
            raise ValueError("网址必须是字符串")
        old = sorted(set(expected_urls))
        new = sorted(set(urls))
        for url in new:
            url_syntax(url)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            current = self.seeds(cid, year)
            if current != old:
                raise ValueError("已保存网址已被其他操作修改，请刷新后重新核对")
            self.conn.execute("DELETE FROM seeds WHERE conference_id=? AND year=?", (cid, year))
            self.conn.executemany("INSERT INTO seeds VALUES (?,?,?)", ((cid, year, url) for url in new))
        return self.seeds(cid, year)

    def seeds(self, cid, year):
        return [r[0] for r in self.conn.execute("SELECT url FROM seeds WHERE conference_id=? AND year=? ORDER BY url", (cid, year))]

    def seed_stats(self):
        total = self.conn.execute("SELECT COUNT(*) FROM conferences").fetchone()[0]
        rows = self.conn.execute("SELECT COUNT(*),COUNT(DISTINCT conference_id) FROM seeds").fetchone()
        by_year = [{"year": row[0], "urls": row[1], "conferences": row[2]}
                   for row in self.conn.execute("""SELECT year,COUNT(*),COUNT(DISTINCT conference_id)
                                                  FROM seeds GROUP BY year ORDER BY year""")]
        return {
            "total_conferences": total,
            "seed_rows": rows[0],
            "conferences_with_seed": rows[1],
            "conferences_without_seed": total - rows[1],
            "by_year": by_year,
        }
    def ingest(self, bundle):
        from .model import require_text
        if not isinstance(bundle, dict):
            raise ValueError("导入内容必须是 JSON 对象")
        cid, year = bundle.get("conference_id"), bundle.get("year")
        require_text(cid, "conference_id", 200)
        self.resolve(cid)
        if type(year) is not int or not 1900 <= year <= 2200:
            raise ValueError("year 必须是 1900–2200 的整数")
        valid, rejected = validate_bundle(bundle, cid, year)
        changes = {"inserted": 0, "updated": 0, "unchanged": 0,
                   "rejected": rejected, "record_ids": []}
        sources = json.dumps(bundle["sources"], ensure_ascii=False, sort_keys=True)
        with self.conn:
            for r in valid:
                changes["record_ids"].append(r["id"])
                payload = json.dumps(r, ensure_ascii=False, sort_keys=True)
                old = self.conn.execute("SELECT * FROM records WHERE id=?", (r["id"],)).fetchone()
                if old and old["payload"] == payload:
                    changes["unchanged"] += 1
                    continue
                if old:
                    self.conn.execute("INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)",
                                      (r["id"], json.dumps(dict(old), ensure_ascii=False), now()))
                self.conn.execute("""INSERT INTO records VALUES (?,?,?,?,?,?,?,'pending',?,?,?,?,NULL,NULL)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,sources=excluded.sources,
                date_start=excluded.date_start,date_end=excluded.date_end,status='pending',
                updated_at=excluded.updated_at,reviewer=NULL,review_note=NULL""",
                (r["id"], cid, year, r["award_type"], r["title"], r["date_start"], r["date_end"],
                 payload, sources, now(), now()))
                changes["updated" if old else "inserted"] += 1
                self.conn.execute("UPDATE coverage SET state='partial',note=?,updated_at=?,expected_count=CASE WHEN expected_count=0 THEN NULL ELSE expected_count END WHERE conference_id=? AND year=? AND award_type=?",
                                  ("新增或修改记录后，覆盖结论需要重新核对", now(), cid, year, r["award_type"]))
        return changes

    def search(self, conference=None, rank=None, year_from=None, year_to=None,
               author=None, affiliation=None, title=None, award=None, status="active",
               published_from=None, published_to=None):
        where, args = [], []
        for field, value, op in [("r.conference_id", conference, "="), ("c.rank", rank, "="),
                                 ("r.year", year_from, ">="), ("r.year", year_to, "<="),
                                 ("r.award_type", award, "="),
                                 ("r.date_end", published_from, ">="), ("r.date_start", published_to, "<=")]:
            if value is not None:
                where.append(f"{field} {op} ?")
                args.append(value)
        if status == "active":
            where.append("r.status!='rejected'")
        elif status != "all":
            where.append("r.status=?")
            args.append(status)
        if title:
            where.append("instr(fold(r.title),?)>0")
            args.append(norm(title))
        sql = "SELECT r.*,c.acronym,c.rank,c.area FROM records r JOIN conferences c ON c.id=r.conference_id"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY r.year DESC, fold(c.acronym), fold(r.title), r.award_type"
        result = []
        for row in self.conn.execute(sql, args):
            item = json.loads(row["payload"])
            # Both person and institution must match the SAME author on a paper.
            if author or affiliation:
                if not any((not author or norm(author) in norm(a["name"])) and
                           (not affiliation or any(norm(affiliation) in norm(b["name"]) for b in a["affiliations"]))
                           for a in item["authors"]):
                    continue
            item.update(acronym=row["acronym"], rank=row["rank"], area=row["area"],
                        status=row["status"], reviewer=row["reviewer"], review_note=row["review_note"],
                        sources=json.loads(row["sources"]), updated_at=row["updated_at"])
            result.append(item)
        return result

    def review(self, rid, state, reviewer, note):
        if state not in ("verified", "rejected", "pending"):
            raise ValueError("未知状态")
        with self.conn:
            old = self.conn.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
            if not old:
                raise ValueError("记录不存在")
            self.conn.execute("INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)",
                              (rid, json.dumps(dict(old), ensure_ascii=False), now()))
            self.conn.execute("UPDATE records SET status=?,reviewer=?,review_note=?,updated_at=? WHERE id=?",
                              (state, reviewer, note, now(), rid))

    def mark_coverage(self, cid, year, award, state, url, note, expected_count=_UNSET):
        from .model import url_syntax
        url_syntax(url)
        if type(year) is not int or not 1900 <= year <= 2200:
            raise ValueError("年份必须在 1900–2200 之间")
        if award not in ("best_paper", "best_student_paper"):
            raise ValueError("奖项类别不正确")
        if state not in ("not_started", "partial", "checked", "not_offered", "not_found"):
            raise ValueError("覆盖状态不正确")
        if not self.conn.execute("SELECT 1 FROM conferences WHERE id=?", (cid,)).fetchone():
            raise ValueError("会议不存在")
        if state == "not_offered" and self.conn.execute("SELECT 1 FROM records WHERE conference_id=? AND year=? AND award_type=? AND status!='rejected' LIMIT 1", (cid, year, award)).fetchone():
            raise ValueError("已有未排除的获奖记录，不能标记该年度未设奖；请先核对记录")
        if expected_count is _UNSET:
            if state == "not_offered":
                expected_count = 0
            else:
                existing = self.conn.execute("SELECT expected_count FROM coverage WHERE conference_id=? AND year=? AND award_type=?",
                                             (cid, year, award)).fetchone()
                expected_count = existing[0] if existing else None
                if expected_count == 0:
                    expected_count = None
        if state == "not_offered":
            if expected_count not in (None, 0):
                raise ValueError("确认未设奖时，获奖总篇数必须为 0")
            expected_count = 0
        elif expected_count is not None and (type(expected_count) is not int or not 1 <= expected_count <= 100000):
            raise ValueError("获奖总篇数应为正整数；未知时留空")
        with self.conn:
            self.conn.execute("""INSERT INTO coverage
                (conference_id,year,award_type,state,evidence_url,note,updated_at,expected_count)
                VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(conference_id,year,award_type) DO UPDATE SET state=excluded.state,
                evidence_url=excluded.evidence_url,note=excluded.note,updated_at=excluded.updated_at,
                expected_count=excluded.expected_count""",
            (cid, year, award, state, url, note, now(), expected_count))

    def coverage(self, start, end, cid=None):
        if type(start) is not int or type(end) is not int or not 1900 <= start <= end <= 2200:
            raise ValueError("年份范围必须在 1900–2200 之间，且开始年份不晚于结束年份")
        return self.coverage_report([cid] if cid else None, range(start, end + 1), limit=None)["rows"]

    def coverage_report(self, conference_ids, years, offset=0, limit=100):
        """Return selected rows and a selection-wide rate only where award totals are known."""
        catalog = self.conferences()
        known_ids = {conf["id"] for conf in catalog}
        if conference_ids is None:
            selected = catalog
        else:
            ids = set(conference_ids)
            if ids - known_ids:
                raise ValueError("包含未知会议")
            selected = [conf for conf in catalog if conf["id"] in ids]
        year_numbers = sorted(set(years))
        if any(type(year) is not int or not 1900 <= year <= 2200 for year in year_numbers):
            raise ValueError("年份必须在 1900–2200 之间")
        if type(offset) is not int or offset < 0 or (limit is not None and (type(limit) is not int or limit < 1)):
            raise ValueError("分页参数不正确")
        summary = dict(targets=2 * len(selected) * len(year_numbers), found_total=0,
                       known_targets=0, unknown_targets=0, not_offered_targets=0,
                       known_found=0, known_expected=0, over_expected_targets=0,
                       coverage_rate=None)
        if not selected or not year_numbers:
            return {"rows": [], "total_rows": 0, "summary": summary}
        ids = [conf["id"] for conf in selected]
        placeholders = ",".join("?" for _ in ids)
        bounds = [*ids, year_numbers[0], year_numbers[-1]]
        decisions = {(row["conference_id"], row["year"], row["award_type"]): row
                     for row in self.conn.execute(
                         f"SELECT * FROM coverage WHERE conference_id IN ({placeholders}) AND year BETWEEN ? AND ?",
                         bounds)}
        counts_by_target = {}
        for row in self.conn.execute(
                f"""SELECT conference_id,year,award_type,status,COUNT(*) AS total
                    FROM records WHERE conference_id IN ({placeholders}) AND year BETWEEN ? AND ?
                    AND award_type IN ('best_paper','best_student_paper')
                    GROUP BY conference_id,year,award_type,status""", bounds):
            counts_by_target.setdefault((row["conference_id"], row["year"], row["award_type"]), {})[row["status"]] = row["total"]
        rows = []
        index = 0
        for conf in selected:
            for year in year_numbers:
                for award in ("best_paper", "best_student_paper"):
                    key = (conf["id"], year, award)
                    decision = decisions.get(key)
                    counts = counts_by_target.get(key, {})
                    found = counts.get("pending", 0) + counts.get("verified", 0)
                    expected = decision["expected_count"] if decision else None
                    summary["found_total"] += found
                    if expected is None:
                        summary["unknown_targets"] += 1
                    elif expected == 0:
                        summary["not_offered_targets"] += 1
                    else:
                        summary["known_targets"] += 1
                        summary["known_found"] += found
                        summary["known_expected"] += expected
                        if found > expected:
                            summary["over_expected_targets"] += 1
                    if index >= offset and (limit is None or len(rows) < limit):
                        rows.append(dict(conference_id=conf["id"], acronym=conf["acronym"], rank=conf["rank"],
                                         year=year, award_type=award,
                                         state=decision["state"] if decision else ("partial" if counts else "not_started"),
                                         counts=counts, found_count=found, expected_count=expected,
                                         coverage_rate=round(found / expected * 100, 1) if expected else None,
                                         evidence_url=decision["evidence_url"] if decision else None,
                                         note=decision["note"] if decision else None))
                    index += 1
        if summary["known_expected"]:
            summary["coverage_rate"] = round(summary["known_found"] / summary["known_expected"] * 100, 1)
        return {"rows": rows, "total_rows": summary["targets"], "summary": summary}

    def start_run(self, cid, year):
        with self.conn:
            return self.conn.execute("INSERT INTO runs(conference_id,year,started_at,status) VALUES (?,?,?,'running')",
                                     (cid, year, now())).lastrowid

    def finish_run(self, run_id, status, details):
        with self.conn:
            self.conn.execute("UPDATE runs SET finished_at=?,status=?,details=? WHERE id=?",
                              (now(), status, json.dumps(details, ensure_ascii=False), run_id))

    def _run_filter(self, started_from=None, started_to=None, conference_id=None, status=None):
        bounds = []
        for value in (started_from, started_to):
            if value:
                try:
                    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        raise ValueError()
                    bounds.append(parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds"))
                except (ValueError, TypeError):
                    raise ValueError("时间范围必须为带时区的 ISO 时间") from None
            else:
                bounds.append(None)
        if bounds[0] and bounds[1] and bounds[0] > bounds[1]:
            raise ValueError("开始时间不得晚于结束时间")
        where, args = ["r.deleted_at IS NULL"], []
        if bounds[0]:
            where.append("r.started_at >= ?")
            args.append(bounds[0])
        if bounds[1]:
            where.append("r.started_at <= ?")
            args.append(bounds[1])
        if conference_id:
            where.append("r.conference_id = ?")
            args.append(conference_id)
        if status:
            where.append("r.status = ?")
            args.append(status)
        return " AND ".join(where), args

    def runs(self, limit=50, started_from=None, started_to=None, conference_id=None, status=None):
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 500):
            raise ValueError("日志数量应在 1–500 之间")
        where, args = self._run_filter(started_from, started_to, conference_id, status)
        sql = """SELECT r.*,c.acronym FROM runs r JOIN conferences c ON c.id=r.conference_id
            WHERE """ + where + " ORDER BY r.id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args = [*args, limit]
        rows = self.conn.execute(sql, args).fetchall()
        result = []
        for row in rows:
            details = json.loads(row["details"] or "{}")
            started = dt.datetime.fromisoformat(row["started_at"]) if row["started_at"] else None
            finished = dt.datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None
            result.append({**dict(row), "details": details,
                           "duration_seconds": (finished - started).total_seconds()
                           if started and finished else None})
        return result

    def run_count(self, started_from=None, started_to=None, conference_id=None, status=None):
        where, args = self._run_filter(started_from, started_to, conference_id, status)
        return self.conn.execute("SELECT COUNT(*) FROM runs r WHERE " + where, args).fetchone()[0]

    def preview_run_deletion(self, started_from, started_to, conference_id=None, status=None):
        if not started_from or not started_to:
            raise ValueError("删除前必须选择完整的开始时间范围")
        where, args = self._run_filter(started_from, started_to, conference_id, status)
        row = self.conn.execute("SELECT COUNT(*),COALESCE(MAX(r.id),0) FROM runs r WHERE " + where + " AND r.status!='running'", args).fetchone()
        return {"count": row[0], "through_id": row[1]}

    def delete_runs(self, started_from, started_to, expected_count, through_id, conference_id=None, status=None):
        if not started_from or not started_to:
            raise ValueError("删除前必须选择完整的开始时间范围")
        if type(expected_count) is not int or expected_count < 0 or type(through_id) is not int or through_id < 0:
            raise ValueError("删除预览参数无效")
        where, args = self._run_filter(started_from, started_to, conference_id, status)
        where += " AND r.status!='running' AND r.id<=?"
        args.append(through_id)
        with self.conn:
            count = self.conn.execute("SELECT COUNT(*) FROM runs r WHERE " + where, args).fetchone()[0]
            if count != expected_count:
                raise ValueError("匹配日志已变化，请重新预览后再删除")
            self.conn.execute("UPDATE runs AS r SET deleted_at=? WHERE " + where, (now(), *args))
        return count
