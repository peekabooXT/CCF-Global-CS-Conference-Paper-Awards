"""Validation is deterministic; a model response is never a verified fact."""
import calendar
import datetime as dt
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

AWARDS = {
    "best paper award": "best_paper",
    "best paper awards": "best_paper",
    "best research paper award": "best_paper",
    "best paper award – research": "best_paper",
    "best paper award - research": "best_paper",
    "best paper award – applied data science": "best_paper",
    "best paper award - applied data science": "best_paper",
    "best student paper award": "best_student_paper",
    "best student paper awards": "best_student_paper",
    "best student paper award – research": "best_student_paper",
    "best student paper award - research": "best_student_paper",
}


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def keytext(value):
    return "".join(c for c in norm(value) if c.isalnum())


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def require_text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} 必须为非空字符串，最长 {limit} 字符")
    return value.strip()


def url_syntax(url):
    require_text(url, "URL", 4000)
    p = urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        raise ValueError("仅接受不含账号密码的 HTTP(S) URL")
    if any(ord(c) < 33 for c in url):
        raise ValueError("URL 不可包含空白或控制字符")
    return url


def date_bounds(value):
    if not value:
        return None, None, "unknown"
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(-\d{2}){0,2}", value):
        raise ValueError("发表日期只能是 YYYY、YYYY-MM、YYYY-MM-DD 或 null")
    parts = list(map(int, value.split("-")))
    year = parts[0]
    if len(parts) == 1:
        lo, hi, precision = dt.date(year, 1, 1), dt.date(year, 12, 31), "year"
    elif len(parts) == 2:
        month = parts[1]
        lo = dt.date(year, month, 1)
        hi, precision = dt.date(year, month, calendar.monthrange(year, month)[1]), "month"
    else:
        lo = hi = dt.date(*parts)
        precision = "day"
    return lo.isoformat(), hi.isoformat(), precision


def validate_bundle(bundle, conference_id, year):
    if not isinstance(bundle, dict) or bundle.get("conference_id") != conference_id or bundle.get("year") != year:
        raise ValueError("提取文件的会议编号或年份与任务不一致")
    sources = bundle.get("sources")
    records = bundle.get("records")
    if not isinstance(sources, list) or not sources or not isinstance(records, list):
        raise ValueError("需要 sources 数组及 records 数组")
    by_id = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("source 必须是对象")
        sid = require_text(source.get("id"), "source.id", 80)
        if sid in by_id:
            raise ValueError("重复的 source.id")
        url_syntax(source.get("url"))
        require_text(source.get("text"), "source.text", 2_000_000)
        if source.get("role") not in ("award", "metadata"):
            raise ValueError("source.role 必须为 award 或 metadata")
        by_id[sid] = source
    if not any(s["role"] == "award" and str(year) in (s["url"] + " " + s["text"]) for s in sources):
        raise ValueError("获奖来源的 URL 或正文没有对应会议年份，需补充年度来源")

    def evidence(item, label, content=None, role=None):
        if not isinstance(item, dict):
            raise ValueError(f"缺少 {label} 的证据")
        source = by_id.get(item.get("source_id"))
        quote = require_text(item.get("quote"), label + ".quote", 5000)
        if not source or (role and source["role"] != role):
            raise ValueError(f"{label} 的来源不存在或类型不匹配")
        if norm(quote) not in norm(source["text"]):
            raise ValueError(f"{label} 引文在来源文本中不存在")
        if content and keytext(content) not in keytext(quote):
            raise ValueError(f"{label} 的引文不包含字段值")
        return {"source_id": source["id"], "quote": quote}

    valid, rejected = [], []
    for idx, raw in enumerate(records):
        try:
            if not isinstance(raw, dict):
                raise ValueError("record 必须是对象")
            title = require_text(raw.get("title"), "title")
            award_name = require_text(raw.get("award_name"), "award_name", 200)
            award_type = AWARDS.get(norm(award_name))
            if not award_type:
                raise ValueError("奖项未在精确白名单中；不自动纳入提名、优秀论文或其他奖项")
            a_ev = evidence(raw.get("award_evidence"), "award", award_name, "award")
            if keytext(title) not in keytext(a_ev["quote"]):
                raise ValueError("获奖证据必须在同一段引文内包含奖项名称和论文标题")
            if any(x in norm(a_ev["quote"]) for x in ("runner-up", "runner up", "honorable mention", "outstanding paper", "nominee", "test of time")):
                raise ValueError("获奖证据混入其他奖项或提名，请提供明确的获奖段落")
            t_ev = evidence(raw.get("title_evidence"), "title", title)
            award_source = by_id[a_ev["source_id"]]
            if keytext(title) not in keytext(award_source["text"]):
                raise ValueError("获奖来源没有出现论文标题")
            authors = raw.get("authors")
            if not isinstance(authors, list):
                raise ValueError("authors 必须是数组；未知时用 []")
            clean_authors = []
            for author in authors:
                name = require_text(author.get("name"), "author.name", 200)
                ne = evidence(author.get("evidence"), "author.name", name)
                affiliations = author.get("affiliations", [])
                if not isinstance(affiliations, list):
                    raise ValueError("affiliations 必须是数组")
                clean_affiliations = []
                for aff in affiliations:
                    aname = require_text(aff.get("name"), "affiliation", 500)
                    ae = evidence(aff.get("evidence"), "affiliation", aname)
                    clean_affiliations.append({"name": aname, "evidence": ae})
                clean_authors.append(dict(name=name, evidence=ne, affiliations=clean_affiliations))
            published = raw.get("publication_date") or None
            lo, hi, precision = date_bounds(published)
            pub_ev = evidence(raw.get("publication_date_evidence"), "publication_date") if published else None
            # Date spelling can differ (e.g. August 2024 / 2024-08). Semantic
            # equivalence and author-affiliation superscripts require human review.
            if published and published[:4] not in pub_ev["quote"]:
                raise ValueError("发表日期引文未出现对应年份")
            track = str(raw.get("track") or "").strip()
            if len(track) > 200:
                raise ValueError("track 太长")
            clean = dict(title=title, conference_id=conference_id, year=year,
                         award_type=award_type, award_name=award_name, track=track,
                         authors=clean_authors, publication_date=published,
                         date_start=lo, date_end=hi, date_precision=precision,
                         publication_date_evidence=pub_ev, award_evidence=a_ev,
                         title_evidence=t_ev, paper_url=None, doi=None)
            for field in ("paper_url", "doi"):
                value = raw.get(field)
                if value:
                    value = require_text(value, field, 4000)
                    if field == "paper_url":
                        url_syntax(value)
                    if not any(value in s["text"] or value == s["url"] for s in sources):
                        raise ValueError(f"{field} 未在来源中出现")
                    clean[field] = value
            # Keep meaningful punctuation: C, C++, and C# must not collapse.
            identity = [conference_id, year, award_type, norm(track), norm(title)]
            clean["id"] = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
            valid.append(clean)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            rejected.append({"index": idx, "title": raw.get("title") if isinstance(raw, dict) else None,
                             "error": str(exc)})
    return valid, rejected
