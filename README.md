# PR Predictor backend

This is the small FastAPI service for the JavaFX PR Predictor project. It stores users, settings, subscriptions, usage, predictions, and result explanations in a relational database.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

SQLite is used by default and creates `pr_predictor.db` in this folder. To use the included MySQL container instead:

```powershell
docker compose up -d mysql
$env:DATABASE_URL = "mysql+pymysql://fastapi_user:fastapi_password@127.0.0.1:5050/fastapi_demo"
python run.py
```

The interactive API page is at `http://127.0.0.1:8000/docs`. The admin page is at `http://127.0.0.1:8000/admin/` and starts with `admin` / `1234`; set `ADMIN_PASSWORD` before the first startup if you want a different seeded password. Change `TOKEN_SECRET` for a shared deployment.

Prediction scores are deliberately deterministic demo scores. They make the frontend workflow usable without a model file or GitHub credentials; the scoring function can later be replaced in `_calculate_scores` in `app.py`.

See [api_docs.md](api_docs.md), [ER_DIAGRAM.md](ER_DIAGRAM.md), and [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md) for the integration contract and database design.
