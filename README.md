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

Signed-in users can change their password with `POST /change-password` and `currentPassword` / `newPassword` (4–128 characters for the new password). The admin page includes a Change password form. All private admin routes are connected to its dashboard, user roles, model controls, and plan controls.

Plans have monthly credits; each successful prediction spends the selected model's credit cost. Admins can edit costs, plan credits, direct model codes, and parent plans at `/admin/`. Defaults: Free = 5 credits/model 1; Plus = 30 credits/models 1–3; Pro = 100 credits/Plus + models 4–6; Ultra = 300 credits/all Pro models. Admin edits survive restart, including a zero-credit plan.

`GET /active-plan` (bearer token) returns the current plan, its models, `creditsUsed`, and `creditsRemaining`. Switching plans keeps credits already spent that month.

Both prediction routes call `https://pr-predictor-backend-gemini-api.onrender.com/analyze` with `{ "pr_url": "https://github.com/owner/repo/pull/123" }`. Set `PR_ANALYZER_TOKEN` in the backend environment before starting it (on Render, add it under Environment). The backend sends this service token; the frontend continues using its normal login token. No local model training, model files, or GitHub token are needed.

`POST /predict` keeps authentication, model access, monthly credits, and history. It stores the full service response and returns the service's independent merge probability and quality score, full `analysis`, and `probabilityNote`. Failed calls do not spend credits. Existing frontend fields such as `mergeProbability` and `qualityScore` still work. Existing prediction history remains readable; startup adds one nullable JSON column automatically.

`POST /predict-dev` calls the same service without authentication, credits, or history, as before. All catalog models now use this single service: `modelId` selects plan access and cost, not an external classifier. The admin's obsolete artifact-key form field has been removed; the API/database field remains as compatibility metadata. The notebooks and CSV are kept as project source material but are not used at runtime.

Verify with `python -m unittest discover -s tests` (install `httpx` for FastAPI's test client).

See [api_docs.md](api_docs.md), [ER_DIAGRAM.md](ER_DIAGRAM.md), and [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md) for the integration contract and database design.
