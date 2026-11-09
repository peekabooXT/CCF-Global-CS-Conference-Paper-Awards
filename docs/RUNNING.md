# Run the reader website locally

**English** | [简体中文](RUNNING.zh-CN.md)

The reader website is generated from the reviewed snapshot at build time. Its overview, search, annual awards, evidence details and CSV exports work on a static web server. No running Python API, database service or model connection is required for visitors.

## Build and serve static files

Use Python 3.12 or later and Node.js 20 or later. The build script uses the Python standard library:

```powershell
cd frontend
npm ci
npm run build
cd ..
python -m http.server 8080 --directory frontend/dist
```

Visit `http://127.0.0.1:8080/`. Upload the complete `frontend/dist/` directory to any static web server for deployment, including its `assets/` directory. `npm run preview` also serves a built site locally.

## Updating data

Replace the reviewed, versioned `data/exports/public-data.json` through the maintenance workflow, then rebuild and publish the complete output. The build verifies the paper count and refuses unverified input. It generates a compact compressed search index and separate evidence and annual-award detail files. Files have content-based names for browser caching; the HTML selects one consistent release.

Filtering, sorting, pagination and CSV generation run in the browser. Switching views reuses the loaded index. Details load only when opened. The refresh-data button reloads the published snapshot.

The initial language is Chinese. The upper-right language control switches immediately and persists the choice in browser storage. `?lang=en` or `?lang=zh` explicitly selects a language.

## Optional compatibility API

The read-only Python API remains available for existing tools. It is optional for the website:

```powershell
python -m pip install -r requirements-public.txt
python scripts/prepare_data.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`prepare_data.py` refuses to overwrite an existing database. Preserve it before preparing a newer snapshot.

## Validation

```powershell
python scripts/validate_public_snapshot.py
node --test frontend/tests/*.test.js
```

Checks cover verified data, paper counts, index timestamps and database read-only constraints. Frontend tests include translation and CSV identity checks. The viewer searches, browses and exports data; it does not modify paper records.
