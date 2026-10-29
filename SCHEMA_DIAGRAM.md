# Relational Schema Diagram

This is the schema declared in [models.py](models.py). [database.py](database.py) uses SQLite by default or the configured `DATABASE_URL`. Startup creates missing tables and adds supported missing columns through `migrate_schema()` in [app.py](app.py).

`PK` = primary key, `FK` = foreign key, `UQ` = unique column. A `?` after a field name means it is nullable. Each arrow points from a foreign-key column to the referenced table's primary key. SQL types, lengths, and numeric precision come from the current model definitions.

```mermaid
flowchart LR
    users["users<br/>PK user_id : VARCHAR(36)<br/>UQ username : VARCHAR(80)<br/>UQ email : VARCHAR(255)<br/>password_hash : VARCHAR(255)<br/>full_name : VARCHAR(150)<br/>role : VARCHAR(20)<br/>github_profile_url? : TEXT<br/>created_at : DATETIME<br/>updated_at : DATETIME"]
    user_settings["user_settings<br/>PK/FK user_id : VARCHAR(36)<br/>theme_mode : VARCHAR(10)<br/>notifications_enabled : BOOLEAN<br/>default_prediction_type : VARCHAR(30)<br/>default_input_mode : VARCHAR(30)<br/>updated_at : DATETIME"]
    plans["plans<br/>PK plan_id : VARCHAR(36)<br/>UQ code : VARCHAR(80)<br/>name : VARCHAR(150)<br/>monthly_prediction_limit? : INTEGER<br/>monthly_credits : INTEGER<br/>FK parent_plan_id? : VARCHAR(36)<br/>description : TEXT<br/>active : BOOLEAN"]
    plan_model_access["plan_model_access<br/>PK/FK plan_id : VARCHAR(36)<br/>PK/FK model_id : VARCHAR(36)"]
    models["models<br/>PK model_id : VARCHAR(36)<br/>UQ code : VARCHAR(80)<br/>name : VARCHAR(150)<br/>task_type : VARCHAR(30)<br/>version : VARCHAR(80)<br/>provider? : VARCHAR(100)<br/>description? : TEXT<br/>credit_cost : INTEGER<br/>artifact_key? : VARCHAR(80)<br/>active : BOOLEAN<br/>created_at : DATETIME<br/>retired_at? : DATETIME"]
    subscriptions["subscriptions<br/>PK subscription_id : VARCHAR(36)<br/>FK user_id : VARCHAR(36)<br/>FK plan_id : VARCHAR(36)<br/>status : VARCHAR(20)<br/>started_at : DATETIME<br/>ended_at? : DATETIME<br/>provider_reference? : VARCHAR(150)<br/>created_at : DATETIME"]
    usage_periods["usage_periods<br/>PK usage_period_id : VARCHAR(36)<br/>FK user_id : VARCHAR(36)<br/>period_start : DATE<br/>period_end : DATE<br/>predictions_used : INTEGER<br/>limit_snapshot? : INTEGER<br/>credits_used : INTEGER<br/>credit_limit_snapshot : INTEGER"]
    repositories["repositories<br/>PK repository_id : VARCHAR(36)<br/>provider : VARCHAR(50)<br/>owner : VARCHAR(100)<br/>name : VARCHAR(150)<br/>canonical_url : TEXT<br/>created_at : DATETIME"]
    pull_requests["pull_requests<br/>PK pull_request_id : VARCHAR(36)<br/>FK repository_id : VARCHAR(36)<br/>number : INTEGER<br/>UQ url : TEXT<br/>title : TEXT<br/>state : VARCHAR(30)<br/>author_login? : VARCHAR(100)<br/>fetched_at : DATETIME<br/>updated_at : DATETIME"]
    predictions["predictions<br/>PK prediction_id : VARCHAR(36)<br/>FK user_id : VARCHAR(36)<br/>FK usage_period_id : VARCHAR(36)<br/>FK model_id : VARCHAR(36)<br/>FK pull_request_id? : VARCHAR(36)<br/>prediction_type : VARCHAR(30)<br/>status : VARCHAR(20)<br/>model_version : VARCHAR(80)<br/>credits_cost : INTEGER<br/>inference_key? : VARCHAR(80)<br/>created_at : DATETIME<br/>completed_at? : DATETIME<br/>error_message? : TEXT"]
    prediction_inputs["prediction_inputs<br/>PK/FK prediction_id : VARCHAR(36)<br/>input_mode : VARCHAR(30)<br/>github_url? : TEXT<br/>raw_feature_text? : TEXT<br/>submitted_at : DATETIME"]
    prediction_results["prediction_results<br/>PK result_id : VARCHAR(36)<br/>FK/UQ prediction_id : VARCHAR(36)<br/>merge_probability? : NUMERIC(5, 2)<br/>quality_score? : NUMERIC(5, 2)<br/>quality_label? : VARCHAR(30)<br/>recommendation : TEXT<br/>analysis_response? : JSON<br/>generated_at : DATETIME"]
    prediction_features["prediction_features<br/>PK feature_id : VARCHAR(36)<br/>FK prediction_id : VARCHAR(36)<br/>feature_name : VARCHAR(100)<br/>value_type : VARCHAR(20)<br/>value_text? : TEXT<br/>value_number? : NUMERIC(12, 2)<br/>value_boolean? : BOOLEAN<br/>source : VARCHAR(30)<br/>created_at : DATETIME"]
    prediction_factors["prediction_factors<br/>PK factor_id : VARCHAR(36)<br/>FK result_id : VARCHAR(36)<br/>factor_name : VARCHAR(100)<br/>description : TEXT<br/>impact : VARCHAR(20)<br/>display_order : INTEGER"]

    user_settings -->|user_id| users
    plans -->|parent_plan_id| plans
    plan_model_access -->|plan_id| plans
    plan_model_access -->|model_id| models
    subscriptions -->|user_id| users
    subscriptions -->|plan_id| plans
    usage_periods -->|user_id| users
    pull_requests -->|repository_id| repositories
    predictions -->|user_id| users
    predictions -->|usage_period_id| usage_periods
    predictions -->|model_id| models
    predictions -->|pull_request_id| pull_requests
    prediction_inputs -->|prediction_id| predictions
    prediction_results -->|prediction_id| predictions
    prediction_features -->|prediction_id| predictions
    prediction_factors -->|result_id| prediction_results
```

## Keys and constraints

| Table | Key or uniqueness rule |
| --- | --- |
| `users` | `user_id` is the primary key; `username` and `email` are individually unique. |
| `user_settings` | `user_id` is both the primary key and a foreign key to `users`. |
| `plans` | `plan_id` is the primary key; `code` is unique; the nullable parent references `plans.plan_id`. |
| `models` | `model_id` is the primary key; `code` is unique. |
| `plan_model_access` | Composite primary key `(plan_id, model_id)` prevents duplicate direct grants. Both fields are foreign keys. |
| `subscriptions` | `subscription_id` is the primary key. The application manages the active subscription; the database does not impose one active subscription per user. |
| `usage_periods` | `usage_period_id` is the primary key; `(user_id, period_start)` is unique. |
| `repositories` | `repository_id` is the primary key; `(provider, owner, name)` is unique. |
| `pull_requests` | `pull_request_id` is the primary key; `url` is unique; `(repository_id, number)` is also unique. |
| `predictions` | `prediction_id` is the primary key; references a user, usage period, model, and optionally a PR. |
| `prediction_inputs` | `prediction_id` is both the primary key and a foreign key, allowing at most one input per prediction. |
| `prediction_results` | `result_id` is the primary key; `prediction_id` is a unique foreign key, allowing at most one result per prediction. |
| `prediction_features` | `feature_id` is the primary key; multiple feature rows may reference one prediction. |
| `prediction_factors` | `factor_id` is the primary key; multiple factor rows may reference one result. |

Roles (`USER`/`ADMIN`), non-negative plan credits, positive model costs, and acyclic plan inheritance are validated by application code, not database enum/check constraints. Unique indexes are declared on `users.username` and `users.email`; a non-unique index is declared on `predictions.user_id`.

## Current storage and legacy fields

| Field or table | Current purpose |
| --- | --- |
| `plans.monthly_credits` | The active plan's monthly credit budget. |
| `models.credit_cost` | Cost of one successful prediction using this catalog entry. |
| `usage_periods.credits_used` | Credits already spent by the user in the month; used to enforce the budget. |
| `usage_periods.credit_limit_snapshot` | Budget when usage was created or last charged; current availability uses the active plan's budget. |
| `predictions.credits_cost`, `model_version`, `inference_key` | Values saved at prediction time; new inference keys are `gemini-api`. |
| `prediction_results.analysis_response` | Nullable JSON containing the full hosted service response; null for old predictions without a saved response. |
| `plans.monthly_prediction_limit`, `usage_periods.limit_snapshot` | Compatibility fields from the old prediction-count system; credit checks no longer use them. |
| `models.artifact_key` | Compatibility metadata; no local artifact is loaded. |
| `prediction_inputs.raw_feature_text` | Old manual-input data; new requests store `github_url` with `input_mode = GITHUB_URL`. |
| `prediction_features`, `prediction_factors` | Kept to read older history. New feature/analysis details are stored in the JSON response. |

Fresh databases seed Free with 5 credits and model 1, Plus with 30 credits and models 1–3, Pro with 100 credits and Plus access plus models 4–6, and Ultra with 300 credits and Pro access. Admins can change credits, model costs, and access. These are seed values, not database constraints; there is no current unlimited-plan rule.

There are no separate admin, history, or API-token tables. Admin rights come from `users.role`; history queries the prediction tables; the hosted-service token comes from the `PR_ANALYZER_TOKEN` environment variable. Existing databases are upgraded by additive migrations, so older physical constraints can differ from the current model declarations shown here.
