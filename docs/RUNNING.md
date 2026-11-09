# Run the reader website locally

**English** | [简体中文](RUNNING.zh-CN.md)

The standalone viewer provides reviewed data, indices and a read-only website. It requires no model service, account credentials or write-enabled management API.

## Python backend

Use Python 3.12 or later, preferably in a virtual environment:

```powershell
python -m pip install -r requirements-public.txt
python scripts/prepare_data.py
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`prepare_data.py` creates SQLite from the versioned JSON snapshot. It refuses to overwrite an existing database. Preserve the old database before preparing a newer snapshot.

## Frontend

```powershell
cd frontend
npm ci
npm run build
```

Restart the backend after building, then visit `http://127.0.0.1:8000/`. For frontend development, use `npm run dev` and visit `http://127.0.0.1:5173/`; API requests are forwarded to the local backend.

The initial language is Chinese. The upper-right language control switches immediately and persists the choice in browser storage. `?lang=en` or `?lang=zh` explicitly selects a language.

## Validation

```powershell
python scripts/validate_public_snapshot.py
node --test frontend/tests/*.test.js
```

Checks cover verified data, paper counts, index timestamps and database read-only constraints. Frontend tests include translation and CSV identity checks. The viewer searches, browses and exports data; it does not modify paper records.
