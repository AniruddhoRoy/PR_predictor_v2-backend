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

The interactive API page is at `http://127.0.0.1:8000/docs`. The admin page is at `http://127.0.0.1:8000/admin/` and starts with `admin` / `1234`; set `ADMIN_PASSWORD` before the first startup if you want a different seeded password. Admins can manage model catalog records from the Prediction models section; delete deactivates a model so prediction history remains valid. Change `TOKEN_SECRET` for a shared deployment.

The admin page also works when opened through a separate static server such as VS Code Live Server at `http://127.0.0.1:5500/admin/index.html`. Its API base is configured in the `api-base` meta tag in `admin/index.html` and defaults to `http://127.0.0.1:8000`; start the FastAPI server before signing in.

Plans have monthly credits; each successful prediction spends the selected model's credit cost. Admins can edit costs, plan credits, direct model codes, and parent plans at `/admin/`. Defaults: Free = 5 credits/model 1; Plus = 30 credits/models 1–3; Pro = 100 credits/Plus + models 4–6; Ultra = 300 credits/all Pro models. Admin edits survive restart, including a zero-credit plan.

`GET /active-plan` (bearer token) returns the current plan, its models, `creditsUsed`, and `creditsRemaining`. Switching plans keeps credits already spent that month.

Predictions use the preprocessing and classifiers in `models(notebook)/EDA_MY.ipynb`, trained lazily from `final_df.csv` using the notebook's training split. Models 1–5 match the notebook; model 6 is Extra Trees. Optional saved pipelines go in `trained_models/<artifactKey>.joblib`. Unknown or unavailable models return 503 without charging credits. The first prediction trains the selected model and may be slow. GitHub URL inputs fetch actual PR features; set `GITHUB_TOKEN` for private repositories or higher API limits. Manual features accept the notebook's column names or camelCase aliases.

The notebook target is merge status. `qualityScore` currently reuses merge probability for compatibility; it is not a separately trained quality classifier.

Verify with `python -m unittest discover -s tests` (install `httpx` for FastAPI's test client).

See [api_docs.md](api_docs.md), [ER_DIAGRAM.md](ER_DIAGRAM.md), and [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md) for the integration contract and database design.
