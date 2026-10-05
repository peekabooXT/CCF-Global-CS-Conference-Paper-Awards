# 新版 Vue 前端说明

在**不改动原有 `global_cs_paper_awards_agent/` 核心逻辑和 SQLite 数据库**的前提下，新增了一层 FastAPI + Vue3 外接前端。

## 结构

```
Global-CS-Paper-Awards-Agent/
├─ api.py                  ← 新增：FastAPI 层，把 global_cs_paper_awards_agent 包的方法包成 JSON 接口
├─ run_all.py              ← Windows 一键启动（后端 8000 + 前端 5173）
└─ frontend/               ← 新增：Vite + Vue3 + Element Plus
   ├─ vite.config.js       ← /api 代理到 127.0.0.1:8000
   └─ src/
      ├─ api.js             ← 唯一的 HTTP 封装，所有接口集中在这里
      ├─ App.vue            ← 侧边栏布局 + 顶部统计
      ├─ components/RecordDetail.vue  ← 论文详情（检索/核验复用）
      └─ views/             ← 四个页面：检索 / 采集 / 核验 / 覆盖
```

## 启动

首次先装一次前端依赖（已装过可跳过）：

```powershell
cd frontend
npm install
```

之后每次在项目根目录运行 **`python run_all.py`**，或手动执行：

```powershell
# 终端 1：后端
.venv\Scripts\python.exe -m uvicorn api:app --port 8000

# 终端 2：前端
cd frontend
npm run dev
```

浏览器打开 **http://127.0.0.1:5173**。后端接口文档在 http://127.0.0.1:8000/docs 。

## 已对接的功能

| 页面 | 接口 | 复用的核心方法 |
| --- | --- | --- |
| 论文检索 / CSV 导出 | `POST /api/search`、`GET /api/export/csv` | `Database.search()` |
| 记录核验 | `POST /api/review` | `Database.review()` |
| 采集覆盖 / 标记结论 | `GET /api/coverage`、`POST /api/mark-coverage` | `Database.coverage()` / `mark_coverage()` |
| 保存入口、采集 | `GET/POST /api/seeds`、`POST /api/collect` | `add_seed()` / `collect_one()` / `auto_collect_one()` |
| 导入 JSON、样例 | `POST /api/import`、`POST /api/demo` | `Database.ingest()` / `import_demo()` |

## 与原 Streamlit 版的差异（已知取舍）

- **采集是同步执行**：一次请求跑完才返回（本地单人用足够）。原 Streamlit 版的实时滚动日志在网页上做成了结果区展示；如需实时进度，后续可改 SSE/WebSocket。
- **上传 PDF / 正文文件采集**暂未移植**：当前"采集"页走的是网址和 JSON 导入。原文件上传解析（`read_local_source`）后端能力还在，需要时在 `api.py` 加一个 multipart 接口即可。
- **API Key 不持久化**：在采集页填写，仅随本次请求发送，和原 Streamlit 行为一致。
- 原来的 `streamlit_app.py` 完全保留，可与新版并存，随时回退。
