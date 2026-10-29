# PR Predictor backend

This is the small FastAPI service for the JavaFX PR Predictor project. It stores users, settings, subscriptions, usage, predictions, and result explanations in a relational database.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PR_ANALYZER_TOKEN = "your-service-api-token"
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

Signed-in users can change their password with `POST /change-password` and `currentPassword` / `newPassword` (4â€“128 characters for the new password). The admin page includes a Change password form. All private admin routes are connected to its dashboard, user roles, model controls, and plan controls.

Plans have credits and a duration in days. Each successful prediction spends the selected model's credit cost. Admins can edit costs, credits, duration, and model codes at `/admin/`. New databases seed Free = 5 credits/1 day/model 1; Plus = 30 credits/30 days/models 1–3; Pro = 100 credits/30 days/models 1–6; Ultra = 300 credits/30 days/models 1–6. Models are assigned directly. Admin edits survive restart, including a zero-credit plan.

`GET /active-plan` returns the current plan, its models, `creditsUsed`, and `creditsRemaining`. `/subscription` includes `endedAt`. Switching plans keeps credits already spent; selecting the same active plan does not restart it. Expiry starts a fresh Free subscription on the next plan-dependent request. Editing a duration applies to new subscriptions.

Both prediction routes call `https://pr-predictor-backend-gemini-api.onrender.com/analyze` with `{ "pr_url": "https://github.com/owner/repo/pull/123" }`. Set `PR_ANALYZER_TOKEN` in the backend environment before starting it (on Render, add it under Environment). The backend sends this service token; the frontend continues using its normal login token. No local model training, model files, or GitHub token are needed.

Both `POST /predict` and `POST /predict-dev` return the complete `/analyze` JSON unchanged: `pr_url`, `features`, `analysis`, `probability_note`, and any additional service fields. No local response fields are added and no analyzer fields are renamed or filtered. The scores are `analysis.merge_probability` and `analysis.quality_score`, regardless of predictionType.

`POST /predict` keeps authentication, model access, plan credits, and history. It stores the full response and charges only successful predictions. Use `/history` for local prediction IDs and `/active-plan` for remaining credits. History includes the PR URL, title, scores, features, and analysis. The old factors list is removed.

`POST /predict-dev` calls the same service without authentication, credits, or history, as before. All catalog models now use this single service: `modelId` selects plan access and cost, not an external classifier. Model task types and artifact keys are removed.

Verify with `python -m unittest discover -s tests` (install `httpx` for FastAPI's test client).

See [api_docs.md](api_docs.md), [ER_DIAGRAM.md](ER_DIAGRAM.md), and [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md) for the integration contract and database design.
