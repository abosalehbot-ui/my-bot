# Local run + Railway deployment notes

## Local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn web:app --host 0.0.0.0 --port 8000
```

## Quality checks
```bash
python -m py_compile web.py store_routes.py main.py handlers.py database.py config.py keyboards.py
node --check static/js/store.js
pytest -q
```

## Railway
- Start command: `uvicorn web:app --host 0.0.0.0 --port $PORT`
- Health endpoint: `/healthz`
- Required envs observed in project:
  - `MONGO_URI` (from `config.py`)
  - `SECRET_TOKEN` (admin auth)
  - `ADMIN_USER`, `ADMIN_PASS` (optional overrides)
