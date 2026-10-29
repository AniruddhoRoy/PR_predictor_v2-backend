# Entity Relationship Diagram

Based on the current SQLAlchemy models in [models.py](models.py) and the prediction workflow in [app.py](app.py). All 14 tables and all their columns are shown, including fields retained for older data.

`PK` = primary key, `FK` = foreign key, `UK` = unique key. Fields marked `nullable` can be empty; the other fields are required by the model. Composite keys and SQL types are detailed in [SCHEMA_DIAGRAM.md](SCHEMA_DIAGRAM.md).

```mermaid
erDiagram
    USERS ||--o| USER_SETTINGS : has
    USERS ||--o{ SUBSCRIPTIONS : owns
    PLANS ||--o{ SUBSCRIPTIONS : defines
    PLANS o|--o{ PLANS : parent_of
    PLANS ||--o{ PLAN_MODEL_ACCESS : grants
    MODELS ||--o{ PLAN_MODEL_ACCESS : included_in
    USERS ||--o{ USAGE_PERIODS : tracks
    USERS ||--o{ PREDICTIONS : submits
    USAGE_PERIODS ||--o{ PREDICTIONS : accounts_for
    MODELS ||--o{ PREDICTIONS : prices
    REPOSITORIES ||--o{ PULL_REQUESTS : contains
    PULL_REQUESTS o|--o{ PREDICTIONS : analyzed_by
    PREDICTIONS ||--o| PREDICTION_INPUTS : has_input
    PREDICTIONS ||--o| PREDICTION_RESULTS : has_result
    PREDICTIONS ||--o{ PREDICTION_FEATURES : has_legacy_features
    PREDICTION_RESULTS ||--o{ PREDICTION_FACTORS : has_legacy_factors

    USERS {
        string user_id PK
        string username UK
        string email UK
        string password_hash
        string full_name
        string role "USER or ADMIN; checked by the application"
        text github_profile_url "nullable"
        datetime created_at
        datetime updated_at
    }

    USER_SETTINGS {
        string user_id PK, FK
        string theme_mode
        boolean notifications_enabled
        string default_prediction_type
        string default_input_mode
        datetime updated_at
    }

    PLANS {
        string plan_id PK
        string code UK
        string name
        integer monthly_prediction_limit "nullable; legacy count field"
        integer monthly_credits "current monthly budget"
        string parent_plan_id FK "nullable; inherits model access from this plan"
        text description
        boolean active
    }

    PLAN_MODEL_ACCESS {
        string plan_id PK, FK
        string model_id PK, FK
    }

    MODELS {
        string model_id PK
        string code UK
        string name
        string task_type
        string version
        string provider "nullable"
        text description "nullable"
        integer credit_cost "credits per successful prediction"
        string artifact_key "nullable; legacy metadata; ignored by hosted analyzer"
        boolean active
        datetime created_at
        datetime retired_at "nullable"
    }

    SUBSCRIPTIONS {
        string subscription_id PK
        string user_id FK
        string plan_id FK
        string status
        datetime started_at
        datetime ended_at "nullable"
        string provider_reference "nullable"
        datetime created_at
    }

    USAGE_PERIODS {
        string usage_period_id PK
        string user_id FK
        date period_start
        date period_end
        integer predictions_used
        integer limit_snapshot "nullable; legacy count snapshot"
        integer credits_used
        integer credit_limit_snapshot "budget at last successful charge"
    }

    REPOSITORIES {
        string repository_id PK
        string provider
        string owner
        string name
        text canonical_url
        datetime created_at
    }

    PULL_REQUESTS {
        string pull_request_id PK
        string repository_id FK
        integer number
        text url UK
        text title
        string state
        string author_login "nullable"
        datetime fetched_at
        datetime updated_at
    }

    PREDICTIONS {
        string prediction_id PK
        string user_id FK
        string usage_period_id FK
        string model_id FK
        string pull_request_id FK "nullable"
        string prediction_type
        string status
        string model_version
        integer credits_cost "cost charged for this prediction"
        string inference_key "nullable; gemini-api for new predictions"
        datetime created_at
        datetime completed_at "nullable"
        text error_message "nullable"
    }

    PREDICTION_INPUTS {
        string prediction_id PK, FK
        string input_mode
        text github_url "nullable"
        text raw_feature_text "nullable; legacy manual input"
        datetime submitted_at
    }

    PREDICTION_RESULTS {
        string result_id PK
        string prediction_id FK, UK
        decimal merge_probability "nullable"
        decimal quality_score "nullable"
        string quality_label "nullable"
        text recommendation
        json analysis_response "nullable; complete hosted service response"
        datetime generated_at
    }

    PREDICTION_FEATURES {
        string feature_id PK
        string prediction_id FK
        string feature_name
        string value_type
        text value_text "nullable"
        decimal value_number "nullable"
        boolean value_boolean "nullable"
        string source
        datetime created_at
    }

    PREDICTION_FACTORS {
        string factor_id PK
        string result_id FK
        string factor_name
        text description
        string impact
        integer display_order
    }
```

## How the relationships are used

- **Admin access:** an admin is a row in `users` with `role = ADMIN`. There is no separate admin table.
- **Plan access:** `plan_model_access` assigns models directly to a plan. `plans.parent_plan_id` adds the parent plan's models, recursively. Inheritance changes model access, not the monthly credit budget.
- **Credits:** each user has at most one `usage_periods` row per calendar month. A successful `/predict` request adds the chosen model's `credit_cost` to `credits_used` and records that cost in `predictions.credits_cost`. Switching plans keeps the month's existing usage.
- **Analysis and history:** the backend calls the hosted `/analyze` service. It saves repository/PR metadata, a prediction, its input URL, and a result. `prediction_results.analysis_response` holds the complete response, including features, analysis, and `probability_note`. `/predict-dev` does not save records or charge credits.
- **Older history:** `prediction_features` and `prediction_factors` remain for older predictions. New predictions store features and explanations in `analysis_response` instead. Models are catalog entries for access and cost; every entry uses the same hosted service.

The optional one-to-one links reflect the database constraints: the schema permits a user without settings and a prediction without an input/result. The normal application workflow creates those rows. `predictions.pull_request_id` is nullable for compatibility with old records; new predictions always use a GitHub PR.
