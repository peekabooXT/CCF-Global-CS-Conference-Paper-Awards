"""Public website: reviewed paper search, annual awards and source provenance."""
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from paper_awards.database import Database
from paper_awards.award_events import event_detail, list_events
from paper_awards.source_listings import list_source_listings, source_listing_detail
from paper_awards.paper_search import award_names, search_papers, paper_provenance
from paper_awards.ontology import CATEGORIES
from paper_awards.web_helpers import AWARDS, csv_bytes, validate_filters

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="CCF Global CS Conference Best Paper Awards API", docs_url=None, redoc_url=None)


def get_db():
    return Database(os.getenv("AWARDS_PUBLIC_DB", str(ROOT / "data/public.sqlite3")))


def publication():
    path = ROOT / "data/publication.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


@app.exception_handler(ValueError)
async def invalid(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/meta")
def meta():
    db = get_db()
    try:
        return {"mode": "public", "awards": AWARDS, "statuses": {"verified": "已核验"},
                "conferences": db.conferences(), "award_categories": CATEGORIES,
                "award_names": award_names(db.conn), "publication": publication()}
    finally:
        db.close()


class SearchReq(BaseModel):
    conference: Optional[str] = None
    rank: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    author: Optional[str] = None
    affiliation: Optional[str] = None
    title: Optional[str] = None
    award: Optional[str] = None
    award_name: Optional[str] = None
    category: Optional[str] = None
    status: str = "verified"
    published_from: Optional[str] = None
    published_to: Optional[str] = None


def _search(db, req):
    filters = req.model_dump(exclude_none=True)
    filters["status"] = "verified"
    return search_papers(db, validate_filters(filters))


@app.post("/api/search")
def search(req: SearchReq):
    db = get_db()
    try:
        rows = _search(db, req)
        return {"total": len(rows), "records": rows}
    finally:
        db.close()


@app.get("/api/export/csv")
def export(q: str = ""):
    db = get_db()
    try:
        data = csv_bytes(_search(db, SearchReq(**(json.loads(q) if q else {}))))
        return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": "attachment; filename=awards.csv"})
    finally:
        db.close()


@app.get("/api/papers/{record_id}/sources")
def paper_sources(record_id: str):
    db = get_db()
    try:
        row = paper_provenance(db.conn, record_id)
        if row is None:
            raise HTTPException(404, "论文不存在或尚未核验")
        return row
    finally:
        db.close()


@app.get("/api/award-events")
def events(venue: str = "", category: str = "", query: str = "", limit: int = 100, offset: int = 0):
    db = get_db()
    try:
        return list_events(db.conn, venue, category, query, limit, offset)
    finally:
        db.close()


@app.get("/api/award-events/{event_id}")
def event(event_id: str):
    db = get_db()
    try:
        row = event_detail(db.conn, event_id)
        if row is None:
            raise HTTPException(404, "获奖事件不存在")
        return row
    finally:
        db.close()


@app.get("/api/source-listings")
def listings(venue: str = "", query: str = "", relation: str = "", limit: int = 50, offset: int = 0):
    db = get_db()
    try:
        return list_source_listings(db.conn, venue, query, relation, limit, offset)
    finally:
        db.close()


@app.get("/api/source-listings/{listing_id}")
def listing(listing_id: str):
    db = get_db()
    try:
        row = source_listing_detail(db.conn, listing_id)
        if row is None:
            raise HTTPException(404, "来源收录不存在")
        return row
    finally:
        db.close()


@app.api_route('/api/{unmatched:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def unknown_api(unmatched: str):
    raise HTTPException(404, '接口不存在')


if (ROOT / 'frontend/dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True), name='website')
