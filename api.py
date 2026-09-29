"""FastAPI 层：只做 JSON 包装，业务逻辑全部复用 ccf_awards 包，不改一行核心代码。

启动（在项目根目录）：
    Global-CS-Paper-Awards-main\\Scripts\\python.exe -m uvicorn api:app --port 8000
然后启动前端：frontend 目录下 npm run dev（Vite 会把 /api 代理到 8000）。
"""
from __future__ import annotations

import json as json_lib
import queue
import tempfile
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from ccf_awards.__main__ import auto_collect_one, collect_one
from ccf_awards.db import Database
from ccf_awards.award_events import event_detail, list_events
from ccf_awards.ontology import CATEGORIES
from ccf_awards.paper_search import award_names, search_papers
from ccf_awards.source_listings import list_source_listings, source_listing_detail
from ccf_awards.discovery import ResponsesWebSearch
from ccf_awards.llm import LLM
from ccf_awards.network import read_local_source
from ccf_awards.web_helpers import (
    AWARDS,
    COVERAGE,
    STATUSES,
    csv_bytes,
    database_path,
    import_demo,
    run_log_csv_bytes,
    validate_filters,
)

app = FastAPI(title="Global CS Paper Awards API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Database:
    """每次新建连接，且在线程内创建使用（SQLite 不跨线程共享连接）。"""
    db = Database(database_path())
    if not db.conferences():
        db.init()
    return db


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    """核心层抛的 ValueError（参数校验、歧义、冲突等）统一转成 400。"""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- 基础元数据 ----------

@app.get("/api/meta")
def meta():
    db = get_db()
    try:
        return {
            "awards": AWARDS,
            "statuses": STATUSES,
            "coverage": COVERAGE,
            "conferences": db.conferences(),
            "award_categories": CATEGORIES,
            "award_names": award_names(db.conn),
        }
    finally:
        db.close()


@app.get("/api/award-events")
def award_events(venue: str = "", category: str = "", query: str = "",
                 limit: int = 100, offset: int = 0):
    db = get_db()
    try:
        return list_events(db.conn, venue, category, query, limit, offset)
    finally:
        db.close()


@app.get("/api/award-events/{event_id}")
def award_event(event_id: str):
    db = get_db()
    try:
        event = event_detail(db.conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="获奖事件不存在")
        return event
    finally:
        db.close()


@app.get("/api/source-listings")
def source_listings(venue: str = "", query: str = "", relation: str = "",
                    limit: int = 50, offset: int = 0):
    db = get_db()
    try:
        return list_source_listings(db.conn, venue, query, relation, limit, offset)
    finally:
        db.close()


@app.get("/api/source-listings/{listing_id}")
def source_listing(listing_id: str):
    db = get_db()
    try:
        item = source_listing_detail(db.conn, listing_id)
        if item is None:
            raise HTTPException(status_code=404, detail="来源收录不存在")
        return item
    finally:
        db.close()


# ---------- 检索 ----------

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
    status: str = "active"
    published_from: Optional[str] = None
    published_to: Optional[str] = None


def _run_search(db: Database, req: SearchReq):
    filters = req.model_dump(exclude_none=True)
    validate_filters(filters)
    return search_papers(db, filters)


@app.post("/api/search")
def search(req: SearchReq):
    db = get_db()
    try:
        records = _run_search(db, req)
        return {"total": len(records), "records": records}
    finally:
        db.close()


@app.get("/api/export/csv")
def export_csv(q: str = ""):
    """GET 导出：查询串即 SearchReq 的 JSON，便于前端直接拼下载链接。"""
    db = get_db()
    try:
        records = _run_search(db, SearchReq(**(json_lib.loads(q) if q else {})))
        return StreamingResponse(
            iter([csv_bytes(records)]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=ccf-awards.csv"},
        )
    finally:
        db.close()


# ---------- 核验 ----------

class ReviewReq(BaseModel):
    id: str
    state: str
    reviewer: str
    note: str


@app.post("/api/review")
def review(req: ReviewReq):
    db = get_db()
    try:
        db.review(req.id, req.state, req.reviewer, req.note)
        return {"ok": True}
    finally:
        db.close()


# ---------- 覆盖 ----------

@app.get("/api/coverage")
def coverage(start: int = 2024, end: int = 2026, cid: Optional[str] = None):
    db = get_db()
    try:
        return {"rows": db.coverage(start, end, cid)}
    finally:
        db.close()


class MarkCoverageReq(BaseModel):
    conference_id: str
    year: int
    award: str
    state: str
    url: str = ""
    note: str = ""


@app.post("/api/mark-coverage")
def mark_coverage(req: MarkCoverageReq):
    db = get_db()
    try:
        db.mark_coverage(req.conference_id, req.year, req.award, req.state, req.url, req.note)
        return {"ok": True}
    finally:
        db.close()


# ---------- 入口（seeds） ----------

@app.get("/api/seed-stats")
def seed_stats():
    db = get_db()
    try:
        return db.seed_stats()
    finally:
        db.close()


@app.get("/api/seeds/{cid}/{year}")
def get_seeds(cid: str, year: int):
    db = get_db()
    try:
        return {"urls": db.seeds(cid, year)}
    finally:
        db.close()


class AddSeedReq(BaseModel):
    conference_id: str
    year: int
    url: str


@app.post("/api/seeds")
def add_seed(req: AddSeedReq):
    db = get_db()
    try:
        db.add_seed(req.conference_id, req.year, req.url)
        return {"ok": True}
    finally:
        db.close()


# ---------- 采集（共享核心 + SSE 流式） ----------

class LLMConfig(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    json_mode: bool = True
    provider: Optional[str] = None


class CollectReq(BaseModel):
    conference_id: str
    year: int
    strategy: str = "urls"          # "urls"=用已填网址；"auto"=自动搜索官网
    urls: list[str] = []
    extra_urls: list[str] = []
    max_pages: int = 4
    llm: LLMConfig = LLMConfig()


def _build_llm(cfg: LLMConfig):
    return LLM(
        api_key=cfg.api_key or None,
        base_url=cfg.base_url or None,
        model=cfg.model or None,
        json_mode=cfg.json_mode,
        provider=cfg.provider or None,
    )


def _do_collect(db: Database, req: CollectReq, notify, local_sources=None):
    """网址/自动/文件 三种采集共用这一段；notify 用于实时回传进度。"""
    conf = next((c for c in db.conferences() if c["id"] == req.conference_id), None)
    if conf is None:
        raise HTTPException(status_code=404, detail="会议不存在")
    llm = _build_llm(req.llm)
    if local_sources is not None:
        return collect_one(db, conf, req.year, [], local_sources=local_sources,
                           max_pages=req.max_pages, llm=llm, notify=notify)
    if req.strategy == "auto":
        if urlsplit(llm.base).hostname == "api.deepseek.com":
            raise ValueError("DeepSeek 官方 API 当前不提供内置 web_search；请使用已有官网网址，或配置支持该工具的 LLM 连接")
        search = ResponsesWebSearch(
            api_key=llm.key,
            base_url=llm.base,
            model=llm.model,
        )
        return auto_collect_one(
            db, conf, req.year, max_pages=req.max_pages,
            candidate_limit=min(3, req.max_pages), search=search, llm=llm, notify=notify,
        )
    if not req.urls:
        raise ValueError("请至少填写一个官网或获奖页网址")
    return collect_one(db, conf, req.year, req.urls, extra_urls=req.extra_urls,
                       max_pages=req.max_pages, llm=llm, notify=notify)


def _sse(work):
    """在子线程跑阻塞的 work(db, notify)，主线程用 queue + SSE 实时推送日志。"""
    q: queue.Queue = queue.Queue()
    SENTINEL = object()

    def notify(msg):
        q.put({"type": "log", "message": str(msg)})

    def runner():
        db = get_db()
        try:
            result = work(db, notify)
            q.put({"type": "result", "result": result})
        except Exception as exc:  # 线程内异常统一推给前端
            q.put({"type": "error", "message": str(exc)})
        finally:
            db.close()
            q.put(SENTINEL)

    threading.Thread(target=runner, daemon=True).start()

    def gen():
        while True:
            item = q.get()
            if item is SENTINEL:
                break
            yield f"data: {json_lib.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/collect-stream")
def collect_stream(req: CollectReq):
    """网址/自动采集：SSE 实时滚动日志。"""
    return _sse(lambda db, notify: _do_collect(db, req, notify))


@app.post("/api/collect-files-stream")
async def collect_files_stream(
    conference_id: str = Form(...),
    year: int = Form(...),
    max_pages: int = Form(4),
    award_file: UploadFile = File(...),
    award_url: str = Form(...),
    metadata_file: UploadFile | None = File(None),
    metadata_url: str = Form(""),
    llm_provider: str = Form("deepseek"),
    llm_base_url: str = Form(""),
    llm_model: str = Form(""),
    llm_api_key: str = Form(""),
):
    """上传获奖页正文/PDF + 可选论文元数据，SSE 实时滚动。"""
    req = CollectReq(
        conference_id=conference_id, year=year, max_pages=max_pages,
        llm=LLMConfig(api_key=llm_api_key or None, base_url=llm_base_url or None,
                      model=llm_model or None, provider=llm_provider or None),
    )

    # 先把上传文件落临时盘，再交给核心的 read_local_source 解析
    tmpdir = tempfile.mkdtemp(prefix="ccf-upload-")
    sources = []
    award_path = Path(tmpdir) / ("s1" + Path(award_file.filename or "x").suffix.lower())
    award_path.write_bytes(await award_file.read())
    sources.append(read_local_source(award_path, award_url.strip(), "award", "s1"))
    if metadata_file is not None and metadata_file.filename:
        if not metadata_url.strip():
            raise ValueError("上传论文文件时需要同时填写其来源 URL")
        meta_path = Path(tmpdir) / ("s2" + Path(metadata_file.filename).suffix.lower())
        meta_path.write_bytes(await metadata_file.read())
        sources.append(read_local_source(meta_path, metadata_url.strip(), "metadata", "s2"))

    return _sse(lambda db, notify: _do_collect(db, req, notify, local_sources=sources))


# ---------- 导入 / 样例 / 历史 ----------

class ImportReq(BaseModel):
    bundle: dict


@app.post("/api/import")
def import_json(req: ImportReq):
    db = get_db()
    try:
        return db.ingest(req.bundle)
    finally:
        db.close()


@app.post("/api/demo")
def demo():
    db = get_db()
    try:
        return {"results": import_demo(db)}
    finally:
        db.close()


@app.get("/api/runs")
def runs(limit: int = 50):
    db = get_db()
    try:
        return {"runs": db.runs(limit)}
    finally:
        db.close()


@app.get("/api/runs/export/csv")
def export_runs_csv(limit: int = 500):
    """Download recent persisted collection runs, including token usage."""
    db = get_db()
    try:
        return StreamingResponse(
            iter([run_log_csv_bytes(db.runs(limit))]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=ccf-awards-run-logs.csv"},
        )
    finally:
        db.close()
